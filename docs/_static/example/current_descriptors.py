from stem.descriptor.remote import DescriptorDownloader

downloader = DescriptorDownloader()

try:
  for desc in downloader.get_consensus().run():
    print("found relay %s (%s)" % (desc.nickname, desc.fingerprint))
except Exception as exc:
  print("Unable to retrieve the consensus: %s" % exc)
