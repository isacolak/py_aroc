import os
import sys
import time
import pathlib
import logging
import fnmatch
import itertools
import threading
import subprocess
import typing as t
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

_logger: t.Optional[logging.Logger] = None

def _hasLevelHandler(logger: logging.Logger) -> bool:
	"""Check if there is a handler in the logging chain that will handle
	the given logger's effective level.
	"""
	level = logger.getEffectiveLevel()
	current = logger

	while current:
		if any(handler.level <= level for handler in current.handlers):
			return True

		if not current.propagate:
			break

		current = current.parent

	return False


class _ColorStreamHandler(logging.StreamHandler):
	"""On Windows, wrap stream with Colorama for ANSI style support."""

	def __init__(self) -> None:
		try:
			import colorama
		except ImportError:
			stream = None
		else:
			stream = colorama.AnsiToWin32(sys.stderr)

		super().__init__(stream)


def _log(type: str, message: str, *args: t.Any, **kwargs: t.Any) -> None:
	"""Log a message to the 'reloader' logger.

	The logger is created the first time it is needed. If there is no
	level set, it is set to :data:`logging.INFO`. If there is no handler
	for the logger's effective level, a :class:`logging.StreamHandler`
	is added.
	"""
	global _logger

	if _logger is None:
		_logger = logging.getLogger("reloader")

		if _logger.level == logging.NOTSET:
			_logger.setLevel(logging.INFO)

		if not _hasLevelHandler(_logger):
			_logger.addHandler(_ColorStreamHandler())

	getattr(_logger, type)(message.rstrip(), *args, **kwargs)

def _iterModulePaths() -> t.Iterator[str]:
	"""Find the filesystem paths associated with imported modules."""
	for module in list(sys.modules.values()):
		name = getattr(module, "__file__", None)

		if name is None:
			continue

		while not os.path.isfile(name):
			old = name
			name = os.path.dirname(name)

			if name == old:
				break
		else:
			yield name


def _removeByPattern(paths: t.Set[str], excludePatterns: t.Set[str]) -> None:
	for pattern in excludePatterns:
		paths.difference_update(fnmatch.filter(paths, pattern))

def _findWatchdogPaths(
	extraFiles: t.Set[str], excludePatterns: t.Set[str]
) -> t.Iterable[str]:
	"""Find paths for the stat reloader to watch. Looks at the same
	sources as the stat reloader, but watches everything under
	directories instead of individual files.
	"""
	dirs = set()

	for name in itertools.chain(list(sys.path), extraFiles):
		name = os.path.abspath(name)

		if os.path.isfile(name):
			name = os.path.dirname(name)

		dirs.add(name)

	for name in _iterModulePaths():
		dirs.add(os.path.dirname(name))

	_removeByPattern(dirs, excludePatterns)
	return _findCommonRoots(dirs)


def _findCommonRoots(paths: t.Iterable[str]) -> t.Iterable[str]:
	root: t.Dict[str, dict] = {}

	for chunks in sorted((pathlib.PurePath(x).parts for x in paths), key=len, reverse=True):
		node = root

		for chunk in chunks:
			node = node.setdefault(chunk, {})

		node.clear()

	rv = set()

	def _walk(node: t.Mapping[str, dict], path: t.Tuple[str, ...]) -> None:
		for prefix, child in node.items():
			_walk(child, path + (prefix,))

		if not node:
			rv.add(os.path.join(*path))

	_walk(root, ())
	return rv


def _getArgsForReloading() -> t.List[str]:
	"""Determine how the script was executed, and return the args needed
	to execute it again in a new process.
	"""
	rv = [sys.executable]
	pyScript = sys.argv[0]
	args = sys.argv[1:]
	__main__ = sys.modules["__main__"]

	if getattr(__main__, "__package__", None) is None or (
		os.name == "nt"
		and __main__.__package__ == ""
		and not os.path.exists(pyScript)
		and os.path.exists(f"{pyScript}.exe")
	):
		pyScript = os.path.abspath(pyScript)

		if os.name == "nt":
			if not os.path.exists(pyScript) and os.path.exists(f"{pyScript}.exe"):
				pyScript += ".exe"

			if (
				os.path.splitext(sys.executable)[1] == ".exe"
				and os.path.splitext(pyScript)[1] == ".exe"
			):
				rv.pop(0)

		rv.append(pyScript)
	else:
		if sys.argv[0] == "-m":
			args = sys.argv
		else:
			if os.path.isfile(pyScript):
				pyModule = t.cast(str, __main__.__package__)
				name = os.path.splitext(os.path.basename(pyScript))[0]

				if name != "__main__":
					pyModule += f".{name}"
			else:
				pyModule = pyScript

			rv.extend(("-m", pyModule.lstrip(".")))

	rv.extend(args)
	return rv


class WatchdogReloaderLoop:
	def __init__(self,
		extraFiles: t.Optional[t.Iterable[str]] = None,
		excludePatterns: t.Optional[t.Iterable[str]] = None,
		interval: t.Union[int, float] = 1
	) -> None:
		self.extraFiles: t.Set[str] = {os.path.abspath(x) for x in extraFiles or ()}
		self.excludePatterns: t.Set[str] = set(excludePatterns or ())
		self.interval = interval

		triggerReload = self.triggerReload

		class EventHandler(PatternMatchingEventHandler):
			def on_any_event(self, event):
				triggerReload(event.src_path)

		self.observer = Observer()
		extraPatterns = [p for p in self.extraFiles if not os.path.isdir(p)]
		self.eventHandler = EventHandler(
			patterns=["*.py", "*.pyc", "*.zip", *extraPatterns],
			ignore_patterns=[
				"*/__pycache__/*",
				"*/.git/*",
				"*/.hg/*",
				*self.excludePatterns,
			],
		)
		self.shouldReload = False

	def triggerReload(self, filename: str) -> None:
		self.shouldReload = True
		# self.logReload(filename)
	
	def logReload(self, filename: str) -> None:
		filename = os.path.abspath(filename)
		_log("info", f" * Detected change in {filename!r}, reloading")

	def __enter__(self) -> "WatchdogReloaderLoop":
		self.watches: t.Dict[str, t.Any] = {}
		self.observer.start()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.observer.stop()
		self.observer.join()

	def run(self) -> None:
		while not self.shouldReload:
			self.runStep()
			time.sleep(self.interval)

		sys.exit(3)

	def runStep(self) -> None:
		toDelete = set(self.watches)

		for path in _findWatchdogPaths(self.extraFiles, self.excludePatterns):
			if path not in self.watches:
				try:
					self.watches[path] = self.observer.schedule(
						self.eventHandler, path, recursive=True
					)
				except OSError:
					self.watches[path] = None

			toDelete.discard(path)

		for path in toDelete:
			watch = self.watches.pop(path, None)

			if watch is not None:
				self.observer.unschedule(watch)
	
	def restartWithReloader(self) -> int:
		"""Spawn a new Python interpreter with the same arguments as the
		current one, but running the reloader thread.
		"""
		while True:
			_log("info", f" * Change detected. Restarting.")
			args = _getArgsForReloading()
			newEnviron = os.environ.copy()
			newEnviron["RUN_MAIN"] = "true"
			exitCode = subprocess.call(args, env=newEnviron, close_fds=False)

			if exitCode != 3:
				return exitCode

def ensureEchoOn() -> None:
	"""Ensure that echo mode is enabled. Some tools such as PDB disable
	it which causes usability issues after a reload."""
	if sys.stdin is None or not sys.stdin.isatty():
		return

	try:
		import termios
	except ImportError:
		return

	attributes = termios.tcgetattr(sys.stdin)

	if not attributes[3] & termios.ECHO:
		attributes[3] |= termios.ECHO
		termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)


def runWithReloader(
	main_func: t.Callable[[], None],
	extraFiles: t.Optional[t.Iterable[str]] = None,
	excludePatterns: t.Optional[t.Iterable[str]] = None,
	interval: t.Union[int, float] = 1
) -> None:
	"""Run the given function in an independent Python interpreter."""
	import signal

	signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
	reloader = WatchdogReloaderLoop(
		extraFiles=extraFiles, excludePatterns=excludePatterns, interval=interval
	)

	try:
		if os.environ.get("RUN_MAIN") == "true":
			ensureEchoOn()
			t = threading.Thread(target=main_func, args=())
			t.daemon = True

			with reloader:
				t.start()
				reloader.run()
		else:
			sys.exit(reloader.restartWithReloader())
	except KeyboardInterrupt:
		pass