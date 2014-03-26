Determine The Exit You're Using
===============================

Lets say you're using Tor and one day you run into something odd. Maybe a
misconfigured relay, or maybe one that's being malicious. How can you figure
out what exit you're using?

Here's a simple script that prints information about the exits used to service
the requests going through Tor...

::

  import functools

  from stem import StreamStatus
  from stem.control import EventType, Controller

  def main():
    print "Tracking requests for tor exits. Press 'enter' to end."
    print

    with Controller.from_port() as controller:
      controller.authenticate()

      stream_listener = functools.partial(stream_event, controller)
      controller.add_event_listener(stream_listener, EventType.STREAM)

      raw_input()  # wait for user to press enter


  def stream_event(controller, event):
    if event.status == StreamStatus.SUCCEEDED:
      circ = controller.get_circuit(event.circ_id)

      exit_fingerprint = circ.path[-1][0]
      exit_relay = controller.get_network_status(exit_fingerprint)

      print "Exit relay for our connection to %s" % (event.target)
      print "  address: %s:%i" % (exit_relay.address, exit_relay.or_port)
      print "  fingerprint: %s" % exit_relay.fingerprint
      print "  nickname: %s" % exit_relay.nickname
      print "  locale: %s" % controller.get_info("ip-to-country/%s" % exit_relay.address, 'unknown')
      print


  if __name__ == '__main__':
    main()

Now if you make a request over Tor...

::

  % curl --socks4a 127.0.0.1:9050 google.com
  <HTML><HEAD><meta http-equiv="content-type" content="text/html;charset=utf-8">
  <TITLE>301 Moved</TITLE></HEAD><BODY>
  <H1>301 Moved</H1>
  The document has moved
  <A HREF="http://www.google.com/">here</A>.
  </BODY></HTML>

... this script will tell you about the exit...

::

  % python exit_used.py
  Tracking requests for tor exits. Press 'enter' to end.

  Exit relay for our connection to 64.15.112.44:80
    address: 31.172.30.2:443
    fingerprint: A59E1E7C7EAEE083D756EE1FF6EC31CA3D8651D7
    nickname: chaoscomputerclub19
    locale: unknown

