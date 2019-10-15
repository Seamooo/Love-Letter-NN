import socket
import sys
import os
import hashlib
import json
from enum import Enum
from random import randrange
from threading import Thread
from time import sleep

class Card(Enum):
	GUARD = (1,"Guard",5)
	PRIEST = (2,"Priest",2)
	BARON = (3,"Baron",2)
	HANDMAID = (4,"Handmaid",2)
	PRINCE = (5,"Prince",2)
	KING = (6,"King",1)
	COUNTESS = (7,"Countess",1)
	PRINCESS = (8,"Princess",1)

Cards = []
for card in Card:
	Cards.append(card)

#constant that may need updating
start_server_cmd = 'java -cp json-20190722.jar:. loveletter.Server'
#below function returns thread server is running on
def start_server():
	os.system(start_server_cmd)

def start_server_thread():
	server_thread = Thread(target=start_server, args=[])
	server_thread.start()
	return server_thread

def stop_server(server_thread):
	try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	except socket.error as err:
		print('socket creation failed with error %s' % err)

	port = 15000
	try:
		host_ip = socket.gethostbyname('localhost')
	except socket.gaierror:
		print('could not resolve localhost')
		sys.exit()

	sock.connect((host_ip, port))

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
	server_thread.join()

#request handling
def request_islegalaction(socket, drawn, card, target=-1, guess=Card.GUARD):
	drawn_index = drawn.value[0] - 1
	card_index = card.value[0] - 1
	guess_index = guess.value[0] - 1
	action = {'card':card_index, 'target':target, 'guess':guess_index}
	obj = {'request':True, 'func_name':'legal_action', 'parameters':{'action':action, 'drawn':drawn_index}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	return obj['rv']

def request_myindex(socket):
	obj = {'request':True, 'func_name':'get_player_index', 'parameters':{}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	return obj['rv']

def request_card(socket, player_index):
	obj = {'request':True, 'func_name':'get_card', 'parameters':{'player_index':player_index}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	if 'rv' in obj:
		return Cards[obj['rv']]
	#return None for unknown card

def request_iseliminated(socket, player_index):
	obj = {'request':True, 'func_name':'eliminated', 'parameters':{'player_index':player_index}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	return obj['rv']

def request_discards(socket, player_index):
	obj = {'request':True, 'func_name':'get_discards', 'parameters':{'player_index':player_index}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	rv = []
	for card_index in obj['rv']:
		rv.append(Cards[card_index])
	return rv

def request_score(socket, player_index):
	obj = {'request':True, 'func_name':'score', 'parameters':{'player_index':player_index}}
	socket.sendall((json.dumps(obj) + '\n').encode())
	json_in = socket.recv(1024).decode()
	json_in = json_in.rstrip('\n')
	obj = json.loads(json_in)
	return obj['rv']

def process_request(player, obj):
	if obj['func_name'] == 'new_round':
		player.new_round()
	elif obj['func_name'] == 'see':
		player.see()
	elif obj['func_name'] == 'play_card':
		player.play_card(Cards[obj['parameters']['drawn']])

def send_action(socket, card, target, guess):
	action = {'card':card.value[0] - 1, 'target':target, 'guess':guess.value[0] - 1}
	obj = {'request':False,'rv':action}
	socket.sendall((json.dumps(obj) + '\n').encode())

def send_ack(socket):
	socket.sendall((json.dumps({'request':False}) + '\n').encode())

class PlayerInterface(type):
	def __new__(metaclass, name, bases, attrs):
		expected_methods = {'set_init':3, 'new_round':1, 'see':1, 'play_card':2}
		for method in expected_methods:
			if method not in attrs:
				raise TypeError('method %s missing from AgentInterface class' % method)
			if attrs[method].__code__.co_argcount != expected_methods[method]:
				raise TypeError('method %s requires exactly %d arguments (self inclusive)' %(method, expected_methods[method]))
		return super().__new__(metaclass, name, bases, attrs)

def new_game(players):
	try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	except socket.error as err:
		print('socket creation failed with error %s' % err)

	port = 15000
	try:
		host_ip = socket.gethostbyname('localhost')
	except socket.gaierror:
		print('could not resolve localhost')
		sys.exit()
	#add a 5 second timeout for connection
	count = 0
	while(count < 100):
		try:
			sock.connect((host_ip, port))
			break
		except (ConnectionRefusedError, OSError) as e:
			print(e)
		count += 1
		sleep(0.05)
	if(count == 500):
		print('Connection refused')
		sys.exit(1)

	num_players = len(players)
	for player in players:
		player.set_init(sock, num_players)
	rv = [0 for _ in range(num_players)]
	try:
		#verify connection
		json_in = sock.recv(1024).decode()
		json_in = json_in.rstrip('\n')
		obj = json.loads(json_in)
		m = hashlib.sha256()
		m.update(obj['ver_str'].encode(encoding='ascii'))
		hash_str = ''.join('%02x' % int(c) for c in m.digest())
		json_out = {'ver_str':hash_str, 'num_players':num_players}
		outputmsg = (json.dumps(json_out) + '\n').encode()
		sock.sendall(outputmsg)
		#game loop
		while(True):
			json_in = sock.recv(1024).decode()
			json_in = json_in.rstrip('\n')
			obj = json.loads(json_in)
			if(obj['request']):
				process_request(players[obj['parameters']['player_index']],obj)
			elif 'scores' in obj:
				return obj['scores']
			else:
				break
	finally:
		sock.close()
	return rv


if __name__ == '__main__':
	class Player(metaclass=PlayerInterface):
		#must be called before other methods
		def set_init(self, socket, num_players):
			self.socket = socket
			self.num_players = num_players

		def new_round(self):
			self.index = request_myindex(self.socket)
			send_ack(self.socket)

		def see(self):
			send_ack(self.socket)

		def play_card(self, drawn):
			hand = request_card(self.socket, self.index)
			play = hand if randrange(2) == 0 else drawn
			target = randrange(self.num_players)
			guess = Cards[randrange(len(Cards))]
			while not request_islegalaction(self.socket, drawn, play, target, guess):
				play = hand if randrange(2) == 0 else drawn
				target = randrange(self.num_players)
				guess = Cards[randrange(len(Cards))]
			send_action(self.socket, play, target, guess)

	#server_thread = start_server_thread()
	#below is a hacky fix for now
	sleep(2)
	for _ in range(20000):
		players = [Player(4) for _ in range(4)]
		print(new_game(players))
	#stop_server(server_thread)
