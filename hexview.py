#! /usr/bin/env python
#
#   hexview.py  WJ116
#

'''hex file viewer'''

import mmap

import textmode

from textmode import WHITE, YELLOW, GREEN, CYAN, BLUE, MAGENTA, RED, BLACK
from textmode import getch, KEY_ESC, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
from textmode import KEY_PAGEUP, KEY_PAGEDOWN, KEY_HOME, KEY_END
from textmode import debug


class HexWindow(textmode.Window):
    '''hex viewer main window'''

    def __init__(self, x, y, w, h, colors, title=None, border=True):
        '''initialize'''

        super(HexWindow, self).__init__(x, y, w, h, colors, title, border)

        self.data = None
        self.fd = None
        self.mmap = None

        self.address = 0
        self.cursor_x = 0
        self.cursor_y = 0

    def load(self, filename):
        '''load file
        Raises IOError on error
        '''

        self.fd = open(filename)
        self.mmap = mmap.mmap(self.fd.fileno(), 0, access=mmap.ACCESS_READ)
        self.data = bytearray(self.mmap)

        self.title = filename
        if len(self.title) > self.bounds.w:
            self.title = self.title[:self.bounds.w - 3] + '...'

    def close(self):
        '''close window'''

        self.data = None
        self.mmap = None
        self.fd.close()

        super(HexWindow, self).close()

    def draw(self):
        '''draw the window'''

        if not self.flags & textmode.Window.SHOWN:
            return

        super(HexWindow, self).draw()
        self.draw_hex()

    def draw_hex(self):
        '''draw hexdump'''

        y = 0
        while y < self.bounds.h:
            self.draw_address(y)
            self.draw_bytes(y)
            self.draw_ascii(y)
            y += 1

    def draw_address(self, y):
        '''draw address for line y'''

        self.puts(0, y, '%08X' % (self.address + y * 16), self.colors.text)

    def draw_bytes(self, y):
        '''draw bytes for line y'''

        # two side-by-side groups of 8 bytes

        x = 10
        for i in xrange(0, 8):
            try:
                self.puts(x, y, '%02X' % self.data[self.address + y * 16 + i],
                          self.colors.text)
            except IndexError:
                self.puts(x, y, '   ')
            x += 3
        
        x += 1
        for i in xrange(0, 8):
            try:
                self.puts(x, y, '%02X' % self.data[self.address + y * 16 + i],
                          self.colors.text)
            except IndexError:
                self.puts(x, y, '   ')
            x += 3

    def draw_ascii(self, y):
        '''draw ascii bytes for line y'''

        x = 60
        for i in xrange(0, 16):
            try:
                ch = self.data[self.address + y * 16 + i]
                if ch >= ord(' ') and ch <= ord('~'):
                    ch = chr(ch)
                else:
                    # TODO also set other color?
                    ch = '.'
            except IndexError:
                ch = ' '

            self.putch(x + i, y, ch, self.colors.text)

    def draw_cursor(self, color=-1):
        '''draw cursor'''

        if color == -1:
            color = self.colors.cursor

        # draw hex bytes cursor
        x = 10 + self.cursor_x * 3
        if self.cursor_x >= 8:
            x += 1
        y = self.cursor_y
        try:
            ch = self.data[self.address + y * 16 + self.cursor_x]
        except IndexError:
            # FIXME IndexError due to cursor movement should be prevented
            ch = ord(' ')
        else:
            self.puts(x, y, '%02X' % ch, color)

        # draw ascii cursor
        x = 60 + self.cursor_x
        if ch >= ord(' ') and ch <= ord('~'):
            ch = chr(ch)
        else:
            ch = '.'

        self.putch(x, y, ch, color)

    def clear_cursor(self):
        '''clear the cursor'''

        self.draw_cursor(self.colors.text)

    def scroll_up(self, nlines=1):
        '''scroll nlines up'''

        self.address -= nlines * 16
        if self.address < 0:
            self.address = 0

        self.draw()

    def scroll_down(self, nlines=1):
        '''scroll nlines down'''

        addr = self.address + nlines * 16

        # round up to nearest 16
        num = len(self.data)
        remainder = num % 16
        if remainder > 0:
            num += 16 - remainder

        top = num - self.bounds.h * 16
        if addr > top:
            addr = top

        if addr != self.address:
            self.address = addr
            self.draw()

    def move_up(self):
        '''move cursor up'''

        if not self.cursor_y and not self.address:
            return

        self.clear_cursor()

        if not self.cursor_y:
            self.scroll_up()
        else:
            self.cursor_y -= 1

        self.draw_cursor()

    def move_down(self):
        '''move cursor down'''

        if self.cursor_y >= self.bounds.h - 1:
            # scroll down
            addr = self.address
            self.scroll_down()
            if self.address == addr:
                # no change (already at end)
                return

            self.draw_cursor()
        else:
            self.clear_cursor()
            self.cursor_y += 1
            self.draw_cursor()

    def move_left(self):
        '''move cursor left'''

        if not self.cursor_x and not self.cursor_y:
            if not self.address:
                return

            self.scroll_up()
        else:
            self.clear_cursor()

        if not self.cursor_x:
            if self.cursor_y > 0:
                self.cursor_y -= 1
            self.cursor_x = 15
        else:
            self.cursor_x -= 1

        self.draw_cursor()

    def move_right(self):
        '''move cursor right'''

        if self.cursor_x >= 15 and self.cursor_y >= self.bounds.h - 1:
            # scroll down
            addr = self.address
            self.scroll_down()
            if self.address == addr:
                # no change (already at end)
                return
        else:
            self.clear_cursor()

        if self.cursor_x >= 15:
            self.cursor_x = 0
            if self.cursor_y < self.bounds.h - 1:
                self.cursor_y += 1
        else:
            self.cursor_x += 1

        self.draw_cursor()

    def pageup(self):
        '''page up'''

        if not self.address:
            if not self.cursor_y:
                return

            self.clear_cursor()
            self.cursor_y = 0
            self.draw_cursor()
            return

        self.scroll_up(self.bounds.h - 1)
        self.draw_cursor()

    def pagedown(self):
        '''page down'''

        addr = self.address

        self.scroll_down(self.bounds.h - 1)

        if self.address == addr:
            # no change
            if self.cursor_y >= self.bounds.h - 1:
                return

            self.clear_cursor()
            self.cursor_y = self.bounds.h - 1

        self.draw_cursor()

    def goto_top(self):
        '''go to top'''

        if not self.address:
            if not self.cursor_x and not self.cursor_y:
                return

            self.clear_cursor()
        else:
            self.address = 0
            self.draw()

        self.cursor_x = self.cursor_y = 0
        self.draw_cursor()

    def goto_bottom(self):
        '''go to last page'''

        # round up to nearest 16
        num = len(self.data)
        remainder = num % 16
        if remainder > 0:
            num += 16 - remainder

        top = num - self.bounds.h * 16

        if self.address != top:
            self.address = top
            self.draw()
        else:
            self.clear_cursor()

        self.cursor_x = remainder - 1
        if self.cursor_x < 0:
            self.cursor_x = 15
        self.cursor_y = self.bounds.h - 1
        self.draw_cursor()

    def runloop(self):
        '''run the input loop
        Returns state change code
        '''

        self.gain_focus()
        while True:
            key = getch()

            if key == KEY_ESC:
                self.lose_focus()
                return -1

            elif key == KEY_UP:
                self.move_up()

            elif key == KEY_DOWN:
                self.move_down()

            elif key == KEY_LEFT:
                self.move_left()

            elif key == KEY_RIGHT:
                self.move_right()

            elif key == KEY_PAGEUP:
                self.pageup()

            elif key == KEY_PAGEDOWN:
                self.pagedown()

            elif key == KEY_HOME:
                self.goto_top()

            elif key == KEY_END:
                self.goto_bottom()



def hexview_main():
    '''main program'''

    colors = textmode.ColorSet(BLACK, CYAN)
    colors.cursor = textmode.video_color(WHITE, BLACK, bold=True)

    view = HexWindow(0, 1, 80, 24, colors)
    view.load(sys.argv[1])
    view.show()
    view.runloop()



if __name__ == '__main__':
    import os
    import sys

    if len(sys.argv) <= 1:
        print 'usage: %s <filename>' % os.path.basename(sys.argv[0])
        sys.exit(1)

    textmode.init()
    try:
        hexview_main()
    finally:
        textmode.terminate()

# EOB
