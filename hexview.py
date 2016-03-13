#! /usr/bin/env python
#
#   hexview.py  WJ116
#

'''hex file viewer'''

import curses
import mmap

import textmode

from textmode import WHITE, YELLOW, GREEN, CYAN, BLUE, MAGENTA, RED, BLACK
from textmode import getch, KEY_ESC, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
from textmode import KEY_PAGEUP, KEY_PAGEDOWN, KEY_HOME, KEY_END
from textmode import VIDEO
from textmode import debug


class HexWindow(textmode.Window):
    '''hex viewer main window'''

    OPT_8_BIT = 1
    OPT_16_BIT = 2
    OPT_16_BIT_SWAP = 3
    OPT_32_BIT = 4
    OPT_32_BIT_SWAP = 5

    MODE_SELECT = 1

    # search direction
    FORWARD = 0
    BACKWARD = 1

    def __init__(self, x, y, w, h, colors, title=None, border=True):
        '''initialize'''

        super(HexWindow, self).__init__(x, y, w, h, colors, title, border)

        self.data = None
        self.fd = None
        self.mmap = None

        self.address = 0
        self.cursor_x = self.cursor_y = 0
        self.view_option = HexWindow.OPT_8_BIT
        self.mode = 0
        self.selection_start = self.selection_end = 0
        self.old_addr = old_x = self.old_y = 0

        colors = textmode.ColorSet(WHITE, BLACK)
        colors.cursor = textmode.video_color(WHITE, GREEN, bold=True)
        self.cmdline = textmode.CmdLine(0, VIDEO.h - 1, VIDEO.w, colors,
                                        prompt=':')
        self.search = textmode.CmdLine(0, VIDEO.h - 1, VIDEO.w, colors,
                                       prompt='/')
        self.searchdir = HexWindow.FORWARD

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
        self.draw_statusbar()
        self.draw_hex()

    def draw_statusbar(self):
        '''draw statusbar'''

        status = None
        if self.mode & HexWindow.MODE_SELECT:
            status = 'Select'

        if status is None:
            VIDEO.hline(self.bounds.x + self.bounds.w - 12,
                        self.bounds.y + self.bounds.h, 10, curses.ACS_HLINE,
                        self.colors.border)
        else:
            VIDEO.puts(self.bounds.x + self.bounds.w - 2 - len(status),
                       self.bounds.y + self.bounds.h, status,
                       self.colors.status)

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

        if self.view_option == HexWindow.OPT_8_BIT:
            self.draw_bytes_8bit(y)

        elif self.view_option == HexWindow.OPT_16_BIT:
            self.draw_bytes_16bit(y)

        elif self.view_option == HexWindow.OPT_16_BIT_SWAP:
            self.draw_bytes_16bit_swap(y)

        elif self.view_option == HexWindow.OPT_32_BIT:
            self.draw_bytes_32bit(y)

        elif self.view_option == HexWindow.OPT_32_BIT_SWAP:
            self.draw_bytes_32bit_swap(y)

    def draw_byte_at(self, x, y, addr):
        '''draw a single byte'''

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= addr <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text

        try:
            self.puts(x, y, '%02X' % self.data[addr], color)
        except IndexError:
            self.puts(x, y, '  ', color)

    def draw_bytes_8bit(self, y):
        '''draw single bytes'''

        # two side-by-side groups of 8 bytes

        x = 10
        offset = self.address + y * 16
        for i in xrange(0, 8):
            self.draw_byte_at(x, y, offset)
            x += 2
            if (self.mode & HexWindow.MODE_SELECT and
                    self.selection_start <= offset <= self.selection_end and
                    self.selection_start <= offset + 1 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.putch(x, y, ' ', color)
            offset += 1
            x += 1

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset - 1 <= self.selection_end and
                self.selection_start <= offset <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text
        self.putch(x, y, ' ', color)
        x += 1

        for i in xrange(0, 8):
            self.draw_byte_at(x, y, offset)
            x += 2
            if (i < 7 and self.mode & HexWindow.MODE_SELECT and
                    self.selection_start <= offset <= self.selection_end and
                    self.selection_start <= offset + 1 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.putch(x, y, ' ', color)
            offset += 1
            x += 1

    def draw_bytes_16bit(self, y):
        '''draw 16-bit words'''

        # two side-by-side groups of 4 16-bit words

        x = 10
        offset = self.address + y * 16
        for _ in xrange(0, 4):
            self.draw_byte_at(x, y, offset)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 1 <= self.selection_end and
                    self.selection_start <= offset + 2 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '  ', color)
            offset += 2
            x += 2

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset - 1 <= self.selection_end and
                self.selection_start <= offset <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text
        self.putch(x, y, ' ', color)
        x += 1

        for i in xrange(0, 4):
            self.draw_byte_at(x, y, offset)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            if (i < 3 and self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 1 <= self.selection_end and
                    self.selection_start <= offset + 2 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '  ', color)
            offset += 2
            x += 2

    def draw_bytes_16bit_swap(self, y):
        '''draw 16-bit words, swapped'''

        # two side-by-side groups of 4 16-bit words

        x = 10
        offset = self.address + y * 16
        for _ in xrange(0, 4):
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset)
            x += 2
            if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 1 <= self.selection_end and
                    self.selection_start <= offset + 2 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '  ', color)
            offset += 2
            x += 2

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset - 1 <= self.selection_end and
                self.selection_start <= offset <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text
        self.putch(x, y, ' ', color)
        x += 1

        for i in xrange(0, 4):
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset)
            x += 2
            if (i < 3 and self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 1 <= self.selection_end and
                    self.selection_start <= offset + 2 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '  ', color)
            offset += 2
            x += 2

    def draw_bytes_32bit(self, y):
        '''draw 32-bit words'''

        # four groups of 32-bit words

        x = 10
        offset = self.address + y * 16
        for _ in xrange(0, 2):
            self.draw_byte_at(x, y, offset)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset + 2)
            x += 2
            self.draw_byte_at(x, y, offset + 3)
            x += 2
            if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 3 <= self.selection_end and
                    self.selection_start <= offset + 4 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '    ', color)
            offset += 4
            x += 4

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset - 1 <= self.selection_end and
                self.selection_start <= offset <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text
        self.putch(x, y, ' ', color)
        x += 1

        for i in xrange(0, 2):
            self.draw_byte_at(x, y, offset)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset + 2)
            x += 2
            self.draw_byte_at(x, y, offset + 3)
            x += 2
            if (i < 1 and self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 3 <= self.selection_end and
                    self.selection_start <= offset + 4 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '    ', color)
            offset += 4
            x += 4

    def draw_bytes_32bit_swap(self, y):
        '''draw 32-bit words, byte-swapped'''

        # four groups of 32-bit words

        x = 10
        offset = self.address + y * 16
        for _ in xrange(0, 2):
            self.draw_byte_at(x, y, offset + 3)
            x += 2
            self.draw_byte_at(x, y, offset + 2)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset)
            x += 2
            if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 3 <= self.selection_end and
                    self.selection_start <= offset + 4 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '    ', color)
            offset += 4
            x += 4

        if (self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset - 1 <= self.selection_end and
                self.selection_start <= offset <= self.selection_end):
            # draw selection
            color = self.colors.cursor
        else:
            color = self.colors.text
        self.putch(x, y, ' ', color)
        x += 1

        for i in xrange(0, 2):
            self.draw_byte_at(x, y, offset + 3)
            x += 2
            self.draw_byte_at(x, y, offset + 2)
            x += 2
            self.draw_byte_at(x, y, offset + 1)
            x += 2
            self.draw_byte_at(x, y, offset)
            x += 2
            if (i < 1 and self.mode & HexWindow.MODE_SELECT and
                self.selection_start <= offset + 3 <= self.selection_end and
                    self.selection_start <= offset + 4 <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                color = self.colors.text
            self.puts(x, y, '    ', color)
            offset += 4
            x += 4

    def draw_ascii(self, y):
        '''draw ascii bytes for line y'''

        x = 60
        offset = self.address + y * 16
        for _ in xrange(0, 16):
            invis = False
            try:
                ch = self.data[offset]
                if ch >= ord(' ') and ch <= ord('~'):
                    ch = chr(ch)
                else:
                    invis = True
                    ch = '.'
            except IndexError:
                invis = True
                ch = ' '

            if (self.mode & HexWindow.MODE_SELECT and
                    self.selection_start <= offset <= self.selection_end):
                # draw selection
                color = self.colors.cursor
            else:
                if invis:
                    color = self.colors.invisibles
                else:
                    color = self.colors.text

            self.putch(x, y, ch, color)
            x += 1
            offset += 1

    def draw_cursor(self, clear=False):
        '''draw cursor'''

        if clear:
            color = self.colors.text
        else:
            color = self.colors.cursor

        y = self.cursor_y
        try:
            ch = self.data[self.address + y * 16 + self.cursor_x]
        except IndexError:
            # FIXME IndexError due to cursor movement should be prevented
            ch = ord(' ')

        # position of hex bytes cursor depends on view_option
        if self.view_option == HexWindow.OPT_8_BIT:
            self.draw_cursor_8bit(ch, color)

        elif self.view_option == HexWindow.OPT_16_BIT:
            self.draw_cursor_16bit(ch, color)

        elif self.view_option == HexWindow.OPT_16_BIT_SWAP:
            self.draw_cursor_16bit_swap(ch, color)

        elif self.view_option == HexWindow.OPT_32_BIT:
            self.draw_cursor_32bit(ch, color)

        elif self.view_option == HexWindow.OPT_32_BIT_SWAP:
            self.draw_cursor_32bit_swap(ch, color)

        self.draw_ascii_cursor(ch, color, clear)

    def draw_ascii_cursor(self, ch, color, clear):
        '''draw ascii cursor'''

        if clear:
            color = self.colors.text
        else:
            color = self.colors.cursor

        if ch >= ord(' ') and ch <= ord('~'):
            ch = chr(ch)
        else:
            ch = '.'
            if clear:
                color = self.colors.invisibles

        self.putch(60 + self.cursor_x, self.cursor_y, ch, color)

    def draw_cursor_8bit(self, ch, color):
        '''draw hex bytes cursor'''

        x = 10 + self.cursor_x * 3
        if self.cursor_x >= 8:
            x += 1
        self.puts(x, self.cursor_y, '%02X' % ch, color)

    def draw_cursor_16bit(self, ch, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 2 * 6
        if self.cursor_x & 1:
            x += 2
        if self.cursor_x >= 8:
            x += 1
        self.puts(x, self.cursor_y, '%02X' % ch, color)

    def draw_cursor_16bit_swap(self, ch, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 2 * 6
        if not self.cursor_x & 1:
            x += 2
        if self.cursor_x >= 8:
            x += 1
        self.puts(x, self.cursor_y, '%02X' % ch, color)

    def draw_cursor_32bit(self, ch, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 4 * 12
        mod = self.cursor_x % 4
        x += mod * 2
        if self.cursor_x >= 8:
            x += 1
        self.puts(x, self.cursor_y, '%02X' % ch, color)

    def draw_cursor_32bit_swap(self, ch, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 4 * 12
        mod = self.cursor_x % 4
        x += (3 - mod) * 2
        if self.cursor_x >= 8:
            x += 1
        self.puts(x, self.cursor_y, '%02X' % ch, color)

    def clear_cursor(self):
        '''clear the cursor'''

        self.draw_cursor(clear=True)

    def scroll_up(self, nlines=1):
        '''scroll nlines up'''

        self.address -= nlines * 16
        if self.address < 0:
            self.address = 0

        self.draw()

    def scroll_down(self, nlines=1):
        '''scroll nlines down'''

        addr = self.address + nlines * 16

        pagesize = self.bounds.h * 16
        if addr > len(self.data) - pagesize:
            addr = len(self.data) - pagesize
        if addr < 0:
            addr = 0

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

        self.update_selection()
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
        else:
            self.clear_cursor()
            self.cursor_y += 1

        self.update_selection()
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

        self.update_selection()
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

        self.update_selection()
        self.draw_cursor()

    def roll_left(self):
        '''move left by one byte'''

        if not self.address:
            return

        self.address -= 1
        self.draw()
        self.draw_cursor()

    def roll_right(self):
        '''move right by one byte'''

        # round up to nearest 16
        num = len(self.data)
        remainder = num % 16
        if remainder > 0:
            num += 16 - remainder

        top = num - self.bounds.h * 16
        if self.address < top:
            self.address += 1
            self.draw()
            self.draw_cursor()

    def pageup(self):
        '''page up'''

        if not self.address:
            if not self.cursor_y:
                return

            self.clear_cursor()
            self.cursor_y = 0
            self.update_selection()
            self.draw_cursor()
            return

        if self.cursor_y == self.bounds.h - 1:
            self.clear_cursor()
            self.cursor_y = 0
        else:
            self.scroll_up(self.bounds.h - 1)

        self.update_selection()
        self.draw_cursor()

    def pagedown(self):
        '''page down'''

        if self.cursor_y == 0:
            self.clear_cursor()
            self.cursor_y = self.bounds.h - 1
        else:
            addr = self.address
            self.scroll_down(self.bounds.h - 1)
            if self.address == addr:
                # no change
                if self.cursor_y >= self.bounds.h - 1:
                    return

                self.clear_cursor()
                self.cursor_y = self.bounds.h - 1

        self.update_selection()
        self.draw_cursor()

    def move_home(self):
        '''go to top of document'''

        if not self.address:
            if not self.cursor_x and not self.cursor_y:
                return

            self.clear_cursor()
        else:
            self.address = 0
            self.draw()

        self.cursor_x = self.cursor_y = 0
        self.update_selection()
        self.draw_cursor()

    def move_end(self):
        '''go to last page of document'''

        pagesize = self.bounds.h * 16
        top = len(self.data) - pagesize
        if top < 0:
            top = 0

        if self.address != top:
            self.address = top
            self.draw()
        else:
            self.clear_cursor()

        if len(self.data) < pagesize:
            self.cursor_y = len(self.data) / 16
            self.cursor_x = len(self.data) % 16
        else:
            self.cursor_y = self.bounds.h - 1
            self.cursor_x = 15

        self.update_selection()
        self.draw_cursor()

    def select_view(self, key):
        '''set view option'''

        update = False
        if key == '1' and self.view_option != HexWindow.OPT_8_BIT:
            self.view_option = HexWindow.OPT_8_BIT
            update = True

        elif key == '2' and self.view_option != HexWindow.OPT_16_BIT:
            self.view_option = HexWindow.OPT_16_BIT
            update = True

        elif key == '3' and self.view_option != HexWindow.OPT_16_BIT_SWAP:
            self.view_option = HexWindow.OPT_16_BIT_SWAP
            update = True

        elif key == '4' and self.view_option != HexWindow.OPT_32_BIT:
            self.view_option = HexWindow.OPT_32_BIT
            update = True

        elif key == '5' and self.view_option != HexWindow.OPT_32_BIT_SWAP:
            self.view_option = HexWindow.OPT_32_BIT_SWAP
            update = True

        if update:
            self.draw()
            self.draw_cursor()

    def mode_selection(self):
        '''toggle selection mode'''

        if not self.mode & HexWindow.MODE_SELECT:
            self.selection_start = (self.address + self.cursor_y * 16 +
                                    self.cursor_x)
            self.selection_end = self.selection_start

        self.mode ^= HexWindow.MODE_SELECT
        self.update_selection()

        if not self.mode & HexWindow.MODE_SELECT:
            # was not yet redrawn ... do it now
            self.draw()

        self.draw_cursor()

    def update_selection(self):
        '''update selection start/end'''

        if self.mode & HexWindow.MODE_SELECT:
            old_addr = self.old_addr + self.old_y * 16 + self.old_x
            addr = self.address + self.cursor_y * 16 + self.cursor_x

            if self.selection_start == self.selection_end:
                if addr < self.selection_start:
                    self.selection_start = addr
                elif addr > self.selection_end:
                    self.selection_end = addr
            else:
                if old_addr == self.selection_start:
                    self.selection_start = addr
                elif old_addr == self.selection_end:
                    self.selection_end = addr

            if self.selection_start > self.selection_end:
                # swap start, end
                # and PEP-8 looks amazingly stupid here
                (self.selection_start,
                 self.selection_end) = (self.selection_end,
                                        self.selection_start)

            self.draw()

    def find(self, again=False):
        '''text search'''

        self.searchdir = HexWindow.FORWARD
        searchtext = ''

        if not again:
            self.search.prompt = '/'
            self.search.show()
            ret = self.search.runloop()
            if ret != textmode.ENTER:
                return

            searchtext = self.search.textfield.text
            if not searchtext:
                again = True

        if again:
            try:
                searchtext = self.search.textfield.history[-1]
            except IndexError:
                return

        if not searchtext:
            return

        pos = self.address + self.cursor_y * 16 + self.cursor_x
        if again:
            pos += 1

        try:
            offset = self.data.find(searchtext, pos)
        except ValueError:
            # not found
            offset = -1

        if offset == -1:
            self.search.show()
            self.search.cputs(0, 0, 'Not found',
                              textmode.video_color(WHITE, RED, bold=True))
            getch()
            self.search.hide()
            return

        # text was found at offset
        self.clear_cursor()
        # if on the same page, move the cursor
        pagesize = self.bounds.h * 16
        if self.address < offset + len(searchtext) < self.address + pagesize:
            pass
        else:
            # scroll the page; change base address
            self.address = offset - self.bounds.h * 8
            if self.address > len(self.data) - pagesize:
                self.address = len(self.data) - pagesize
            if self.address < 0:
                self.address = 0

            self.draw()

        # move cursor location
        diff = offset - self.address
        self.cursor_y = diff / 16
        self.cursor_x = diff % 16
        self.draw_cursor()

    def find_backwards(self, again=False):
        '''text search backwards'''

        self.searchdir = HexWindow.BACKWARD
        searchtext = ''

        if not again:
            self.search.prompt = '?'
            self.search.show()
            ret = self.search.runloop()
            if ret != textmode.ENTER:
                return

            searchtext = self.search.textfield.text
            if not searchtext:
                again = True

        if again:
            try:
                searchtext = self.search.textfield.history[-1]
            except IndexError:
                return

        if not searchtext:
            return

        pos = self.address + self.cursor_y * 16 + self.cursor_x
        try:
            offset = bytearray_find_backwards(self.data, searchtext, pos)
        except ValueError:
            # not found
            offset = -1

        if offset == -1:
            self.search.show()
            self.search.cputs(0, 0, 'Not found',
                              textmode.video_color(WHITE, RED, bold=True))
            getch()
            self.search.hide()
            return

        # text was found at offset
        self.clear_cursor()
        # if on the same page, move the cursor
        pagesize = self.bounds.h * 16
        if self.address < offset + len(searchtext) < self.address + pagesize:
            pass
        else:
            # scroll the page; change base address
            self.address = offset - self.bounds.h * 8
            if self.address > len(self.data) - pagesize:
                self.address = len(self.data) - pagesize
            if self.address < 0:
                self.address = 0

            self.draw()

        # move cursor location
        diff = offset - self.address
        self.cursor_y = diff / 16
        self.cursor_x = diff % 16
        self.draw_cursor()

    def move_top(self):
        '''goto top of screen'''

        if self.cursor_y != 0:
            self.clear_cursor()
            self.cursor_y = 0
            self.draw_cursor()

    def move_middle(self):
        '''goto middle of screen'''

        y = self.bounds.h / 2
        if self.cursor_y != y:
            self.clear_cursor()
            self.cursor_y = y
            self.draw_cursor()
    
    def move_bottom(self):
        '''goto bottom of screen'''

        if self.cursor_y != self.bounds.h - 1:
            self.clear_cursor()
            self.cursor_y = self.bounds.h - 1
            self.draw_cursor()

    def runloop(self):
        '''run the input loop
        Returns state change code
        '''

        self.gain_focus()
        while True:
            self.old_addr = self.address
            self.old_x = self.cursor_x
            self.old_y = self.cursor_y

            key = getch()

            if key == KEY_ESC:
                if self.mode & HexWindow.MODE_SELECT:
                    self.mode_selection()

            elif key == KEY_UP:
                self.move_up()

            elif key == KEY_DOWN:
                self.move_down()

            elif key == KEY_LEFT:
                self.move_left()

            elif key == KEY_RIGHT:
                self.move_right()

            elif key == '<' or key == ',':
                self.roll_left()

            elif key == '>' or key == '.':
                self.roll_right()

            elif key == KEY_PAGEUP:
                self.pageup()

            elif key == KEY_PAGEDOWN:
                self.pagedown()

            elif key == KEY_HOME or key == 'g':
                self.move_home()

            elif key == KEY_END or key == 'G':
                self.move_end()

            elif key in ('1', '2', '3', '4', '5'):
                self.select_view(key)

            elif key in ('v', 'V', 'Ctrl-V'):
                self.mode_selection()

            elif key == ':':
                # command mode
                self.cmdline.show()
                ret = self.cmdline.runloop()
                if ret == textmode.RETURN_TO_PREVIOUS:
                    continue

                if self.cmdline.textfield.text in ('q', 'q!', 'quit'):
                    return textmode.QUIT

                if self.cmdline.textfield.text in ('wq', 'wq!', 'ZZ', 'exit'):
                    return textmode.EXIT

            elif key == '?':
                # find backwards
                self.find_backwards()

            elif key == '/' or key == 'Ctrl-F':
                self.find()

            elif key == 'n' or key == 'Ctrl-G':
                # search again
                if self.searchdir == HexWindow.FORWARD:
                    self.find(again=True)
                elif self.searchdir == HexWindow.BACKWARD:
                    self.find_backwards(again=True)

            elif key == '0' or key == '^':
                self.move_begin_line()

            elif key == '$':
                self.move_end_line()

            elif key == 'H':
                self.move_top()

            elif key == 'M':
                self.move_middle()

            elif key == 'L':
                self.move_bottom()



def bytearray_find_backwards(data, search, pos=-1):
    '''search bytearray backwards for string
    Returns index if found or -1 if not found
    May raise ValueError for invalid search
    '''

    if data is None or not len(data):
        raise ValueError

    if search is None or not search:
        raise ValueError

    if pos == -1:
        pos = len(data)

    if pos < 0:
        return ValueError

    pos -= len(search)
    while pos >= 0:
        if data[pos:pos + len(search)] == search:
            return pos

        pos -= 1

    return -1


def hexview_main():
    '''main program'''

    colors = textmode.ColorSet(BLACK, CYAN)
    colors.cursor = textmode.video_color(WHITE, BLACK, bold=True)
    colors.status = colors.cursor
    colors.invisibles = textmode.video_color(BLUE, CYAN, bold=True)

    view = HexWindow(0, 0, 80, VIDEO.h - 1, colors)
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
    VIDEO = textmode.Video()

    try:
        hexview_main()
    finally:
        textmode.terminate()

# EOB
