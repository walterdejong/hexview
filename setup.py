#! /usr/bin/env python3
#
#   setup.py    WJ116
#   for hexview
#
#   Copyright 2016 by Walter de Jong <walter@heiho.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

'''hex file viewer setup'''

from distutils.core import setup

from hexviewlib.hexview import VERSION


setup(name='hexview',
      version=VERSION,
      description='interactive hex viewer',
      author='Walter de Jong',
      author_email='walter@heiho.net',
      url='https://github.com/walterdejong/hexview',
      license='MIT',
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Console :: Curses',
                   'Intended Audience :: Developers',
                   'Intended Audience :: System Administrators',
                   'License :: OSI Approved :: MIT License',
                   'Natural Language :: English',
                   'Operating System :: POSIX',
                   'Operating System :: MacOS :: MacOS X',
                   'Programming Language :: Python :: 2.6',
                   'Topic :: Software Development',
                   'Topic :: System :: Recovery Tools',
                   'Topic :: Utilities'],
      packages=['hexviewlib',],
      package_dir={'hexviewlib': 'hexviewlib'},
      scripts=['hexview',],
      data_files=[('share/doc/hexview', ['LICENSE', 'README.md']),
                  ('share/doc/hexview/master/images', ['images/hexview.png',])]
)

# EOB
