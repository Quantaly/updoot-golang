# updoot-golang

A simple script to manage a Go installation.

Invoking the script with no arguments will attempt to install the latest stable version of Go to the location indicated by the `GOROOT` variable near the top of the file.

Currently it only works on Linux systems with 64-bit processors. This is not a technical limitation, I just don't know what the Python [`platform`](https://docs.python.org/3/library/platform.html) module calls other configurations. Please feel free to submit a pull request if you can provide additional mappings between the Python and Go names for kernels and architectures.
