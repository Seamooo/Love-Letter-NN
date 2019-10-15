from python_interface import PlayerInterface, send_ack, send_action, \
	request_islegalaction, request_myindex, request_card, new_game, Card, Cards
from random import randrange

class RandomAgent(metaclass=PlayerInterface):
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
			#never play princess
			if play == Card.PRINCESS:
				continue
			target = randrange(self.num_players)
			guess = Cards[randrange(len(Cards))]
		send_action(self.socket, play, target, guess)
