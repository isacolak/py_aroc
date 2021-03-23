from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
  name = 'py_aroc',
  packages = ['py_aroc'],
  version = '0.1',
  license='MIT',
  description = 'Python Auto Reload on Change',
  long_description=long_description,
  long_description_content_type="text/markdown",
  author = 'isacolak',
  author_email = 'isacolak04@gmail.com',
  url = 'https://github.com/isacolak/py_aroc',
  download_url = 'https://github.com/isacolak/py_aroc/archive/py_aroc_v_01.tar.gz',
  keywords = ["auto","reload","change","auto reload", "on change","auto reload on change"],
  install_requires=[
    'watchgod',
  ],
  classifiers=[
    'Development Status :: 3 - Alpha',      # "3 - Alpha", "4 - Beta", "5 - Production/Stable"
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9',
  ],
)