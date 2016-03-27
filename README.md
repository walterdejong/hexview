hexview
=======

Interactive console mode hex viewer

![screenshot](master/images/hexview.png)

For the love of console programs ... this hexviewer looks a lot
like a classic DOS program, and/but its user interface is somewhat
inspired by the `vim` editor. For example, get built-in help by typing
'`:help`'. Note, you don't have to hit `Esc` like you would in `vim`.


Using hexview
-------------
You can search text by pressing '`/`' and search backwards with the '`?`'
command, and you may search hexadecimal strings with '`x`'.  
Jump to a particular offset using '`@`'. Use the arrow keys for recalling
search and address history.

Use the number keys '`1`', '`2`', and '`4`' to select different views:
bytes, words, and quadwords.

Hit '`p`' to toggle the printing the values in the subwindow at the bottom.

There's much more, so be sure to read the `:help`.  


Starting hexview
----------------
If you don't like colors, `hexview` may be started with:

    hexview.py --no-colors

See `hexview.py --help` for more options.


Installing hexview
------------------
Run `setup.py install` or use `setup.py bdist` to create a package.


Copyright 2016 by Walter de Jong <walter@heiho.net>

