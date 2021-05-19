# Python Auto Reload on Change

## Installing

Install and update using [pip](https://pip.pypa.io/en/stable/quickstart/):

```sh
pip install py_aroc
```

### A Simple Example

```Python
import py_aroc

d = 10

def main():
 print(d)

py_aroc.runWithReloader(main)
```
