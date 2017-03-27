# Copyright 2015-2017, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Interactive interpreter for interacting with Tor directly. This adds usability
features such as tab completion, history, and IRC-style functions (like /help).
"""

import os
import sys

import stem
import stem.connection
import stem.prereq
import stem.process
import stem.util.conf
import stem.util.system
import stem.util.term

from stem.util.term import Attr, Color, format

__all__ = [
  'arguments',
  'autocomplete',
  'commands',
  'help',
]

PROMPT = format('>>> ', Color.GREEN, Attr.BOLD, Attr.READLINE_ESCAPE)

STANDARD_OUTPUT = (Color.BLUE, Attr.LINES)
BOLD_OUTPUT = (Color.BLUE, Attr.BOLD, Attr.LINES)
HEADER_OUTPUT = (Color.GREEN, Attr.LINES)
HEADER_BOLD_OUTPUT = (Color.GREEN, Attr.BOLD, Attr.LINES)
ERROR_OUTPUT = (Attr.BOLD, Color.RED, Attr.LINES)

settings_path = os.path.join(os.path.dirname(__file__), 'settings.cfg')
uses_settings = stem.util.conf.uses_settings('stem_interpreter', settings_path)


@uses_settings
def msg(message, config, **attr):
  return config.get(message).format(**attr)


def main():
  import readline

  import stem.interpreter.arguments
  import stem.interpreter.autocomplete
  import stem.interpreter.commands

  try:
    args = stem.interpreter.arguments.parse(sys.argv[1:])
  except ValueError as exc:
    print(exc)
    sys.exit(1)

  if args.print_help:
    print(stem.interpreter.arguments.get_help())
    sys.exit()

  if args.disable_color or args.cli:  
    global PROMPT
    stem.util.term.DISABLE_COLOR_SUPPORT = True

    if args.disable_color and not args.cli:
      PROMPT = '>>> '
    elif args.cli:
      PROMPT = ''

  if args.cli:
      def verbose(*output):
        pass
  else:
      def verbose(output):
        print(output)


  # If the user isn't connecting to something in particular then offer to start
  # tor if it isn't running.

  if not (args.user_provided_port or args.user_provided_socket):
    is_tor_running = stem.util.system.is_running('tor') or stem.util.system.is_running('tor.real')

    if not is_tor_running:
      if args.tor_path == 'tor' and not stem.util.system.is_available('tor'):
        print(format(msg('msg.tor_unavailable'), *ERROR_OUTPUT))
        sys.exit(1)
      else:
        verbose(format(msg('msg.starting_tor'), *HEADER_OUTPUT))

        control_port = '9051' if args.control_port == 'default' else str(args.control_port)

        try:
          stem.process.launch_tor_with_config(
            config = {
              'SocksPort': '0',
              'ControlPort': control_port,
              'CookieAuthentication': '1',
              'ExitPolicy': 'reject *:*',
            },
            tor_cmd = args.tor_path,
            completion_percent = 5,
            take_ownership = True,
          )
        except OSError as exc:
          print(format(msg('msg.unable_to_start_tor', error = exc), *ERROR_OUTPUT))
          sys.exit(1)

  control_port = (args.control_address, args.control_port)
  control_socket = args.control_socket

  # If the user explicitely specified an endpoint then just try to connect to
  # that.

  if args.user_provided_socket and not args.user_provided_port:
    control_port = None
  elif args.user_provided_port and not args.user_provided_socket:
    control_socket = None

  controller = stem.connection.connect(
    control_port = control_port,
    control_socket = control_socket,
    password_prompt = True,
  )

  if controller is None:
    sys.exit(1)

  with controller:
    autocompleter = stem.interpreter.autocomplete.Autocompleter(controller)
    readline.parse_and_bind('tab: complete')
    readline.set_completer(autocompleter.complete)
    readline.set_completer_delims('\n')

    interpreter = stem.interpreter.commands.ControlInterpreter(controller)

    for line in msg('msg.startup_banner').splitlines():
      line_format = HEADER_BOLD_OUTPUT if line.startswith('  ') else HEADER_OUTPUT
      verbose(format(line, *line_format))

    verbose('')

    while True:
      try:
        prompt = '... ' if interpreter.is_multiline_context else PROMPT

        if stem.prereq.is_python_3():
          user_input = input(prompt)
        else:
          user_input = raw_input(prompt)

        response = interpreter.run_command(user_input)

        if response is not None:
          print(response)
      except (KeyboardInterrupt, EOFError, stem.SocketClosed) as exc:
        print('')  # move cursor to the following line
        break
