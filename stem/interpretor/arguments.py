# Copyright 2014, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Commandline argument parsing for arm.
"""

import collections
import getopt

DEFAULT_ARGS = { 
  'control_address': '127.0.0.1',
  'control_port': 9051,
  'user_provided_port': False,
  'control_socket': '/var/run/tor/control',
  'user_provided_socket': False,
  'print_help': False,
}

OPT = 'i:s:h'

OPT_EXPANDED = [ 
  'interface=',
  'socket=',
  'help',
]

HELP_OUTPUT = """
Usage prompt [OPTION]
Interactive interpretor for Tor.

  -i, --interface [ADDRESS:]PORT  change control interface from {address}:{port}
  -s, --socket SOCKET_PATH        attach using unix domain socket if present,
                                    SOCKET_PATH defaults to: {socket}
  -h, --help                      presents this help

Example:
prompt -i 1643            attach to control port 1643
prompt -s ~/.tor/socket   attach to a control socket in your home directory
"""

def parse(argv):
  """
  Parses our arguments, providing a named tuple with their values.

  :param list argv: input arguments to be parsed

  :returns: a **named tuple** with our parsed arguments

  :raises: **ValueError** if we got an invalid argument
  """

  args = dict(DEFAULT_ARGS)

  try:
    getopt_results = getopt.getopt(argv, OPT, OPT_EXPANDED)[0]
  except getopt.GetoptError as exc:
    raise ValueError(msg('usage.invalid_arguments', error = exc))

  for opt, arg in getopt_results:
    if opt in ('-i', '--interface'):
      if ':' in arg:
        address, port = arg.split(':', 1)
      else:
        address, port = None, arg

      if address is not None:
        if not stem.util.connection.is_valid_ipv4_address(address):
          raise ValueError(msg('usage.not_a_valid_address', address_input = address))

        args['control_address'] = address

      if not stem.util.connection.is_valid_port(port):
        raise ValueError(msg('usage.not_a_valid_port', port_input = port))

      args['control_port'] = int(port)
      args['user_provided_port'] = True
    elif opt in ('-s', '--socket'):
      args['control_socket'] = arg
      args['user_provided_socket'] = True
    elif opt in ('-h', '--help'):
      args['print_help'] = True

  # translates our args dict into a named tuple

  Args = collections.namedtuple('Args', args.keys())
  return Args(**args)

def get_help():
  """
  Provides our --help usage information.

  :returns: **str** with our usage information
  """

  return HELP_OUTPUT.format(
    address = DEFAULT_ARGS['control_address'],
    port = DEFAULT_ARGS['control_port'],
    socket = DEFAULT_ARGS['control_socket'],
  ).strip()
