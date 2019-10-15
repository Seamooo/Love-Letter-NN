import socket
import sys
import hashlib
import json

try:
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	print('Socket successfully created')
except socket.error as err:
	print('socket creation failed with error %s' % err)

port = 15000
try:
	host_ip = socket.gethostbyname('localhost')
except socket.gaierror:
	print('could not resolve localhost')
	sys.exit()

sock.connect((host_ip, port))

print('socket has successfully connected to the server on port %d' % port)

try:
	json_in = sock.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	m = hashlib.sha256()
	m.update(obj['ver_str'].encode(encoding='ascii'))
	hash_str = ''.join('%02x' % int(c) for c in m.digest())
	json_out = {'ver_str':hash_str, 'num_players':2, 'exit_server':True}
	outputmsg = (json.dumps(json_out) + '\n').encode()
	sock.sendall(outputmsg)
	print('sent exit signal')
finally:
	print('closing socket')
	sock.close()
