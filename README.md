# tflowclient

The ``tflowclient`` package (Text-based workFlow scheduler Client) provides all
the necessary bits to build text-based console clients to interact with
various workflow schedulers. For now, only ``SMS`` is supported: see the
``bin/tflowclient_cdp.py`` executable.

## Requirements & Dependencies

The ``tflowclient`` package is not compatible with Python 2.7.

The ``tflowclient`` package itself only depends on the non-standard ``urwid``
package that is available on PyPi.

To use the ``bin/tflowclient_cdp.py`` executable, a ``cdp`` executable needs to
be available in the system's path. Otherwise, its path can be specified in the
user-specific configuration file ``~/.tflowclientrc.ini``.

## Installation

### Manually

Just fetch the code and add the ``src`` directory to your ``PYTHONPATH``.

### Via ``setuptools``

The ``setuptools`` package can be used:

    python ./setup.py install

It might be advisable to install this package in the user's specific pythons
directories. To do so:

     python ./setup.py install --user

### Test your installation

Use ``nosetests`` manually or launch it through ``setuptools``:

     python ./setup.py test

Once the package is installed, the ``bin/tflowclient_demo.py`` executable
can be launched. It allows you to interact with a dummy workflow.

## The ``~/.tflowclientrc.ini`` configuration file

The configuration file is optional. You do not need to create it unless you
want to customise some the default configuration

It could look like that:

    [logging]
    ; Activate logging in a ``~/.tflowclient.log`` file for messages with a
    ; severity greater or equal to ``CRITICAL``.
    level = CRITICAL
    
    [urwid]
    ; The backend for ``urwid``. The other possible value is ``curses``.
    backend = raw
    
    [palette]
    ; The platette that will be used by urwid.
    ; For example, you might want to print aborted tasks with black
    ; characters on a ``dark magenta`` background
    ABORTED = black,dark magenta

The default ``tflowclient`` palette can be dumped using the
``bin/tflowclient_palette.py`` executable. More details, on the various
color schemes can be obtained in the ``urwid`` documentation.

By default, only 16 colors are available to build the "palette". Some of may
want to expand their horizons... Theoretically, it is possible to support 256
colors (see the configuration) but beware that it is not supported by all
terminals (that's why it's not activated by default).

Use of a 256-colors palette:

    [urwid]
    backend = raw
    terminal_colors = 256
    
    [palette]
    ABORTED = black, dark magenta, , g74, #f86

The first to entries of the palette still represent foreground and background
colors for the 16-colors palette but the 4th and 5th elements represents
foreground and background colors for the 256-colors palette
(see https://urwid.readthedocs.io/en/latest/examples/index.html#palette-test-py).                                                    
