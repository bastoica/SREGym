import geni.portal as portal
from geni.rspec import RSpec

RSPEC_FILE = "rspecs/test.xml"

# Create a Request object to start building the RSpec
request = portal.context.makeRequestRSpec()

#     <description type="markdown">Two c220g5, to deploy distributed training tasks in AIOpsLab</description>
#     <instructions type="markdown">Wait for the profile instance to start, and then log in to either VM via the
# ssh ports specified below.
# </instructions>

# Create two raw "PC" nodes
node1 = request.RawPC("control")
node2 = request.RawPC("compute1")
node3 = request.RawPC("compute2")

# Set hardware type
node1.hardware_type = "m510"
node2.hardware_type = "m510"
node3.hardware_type = "m510"

# Set the disk image
node1.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"
node2.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"
node3.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"

# node1.routable_control_ip = True
# node2.routable_control_ip = True
# node3.routable_control_ip = True

# Create a link between the two nodes
link1 = request.Link(members=[node1, node2, node3])

# Print the RSpec to the console
portal.context.printRequestRSpec()

# Save the RSpec to a file
with open(RSPEC_FILE, "w") as f:
    f.write(request.toXMLString(pretty_print=True, ucode=True))
