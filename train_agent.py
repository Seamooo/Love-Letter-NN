import python_interface
from python_interface import PlayerInterface, send_ack, send_action, \
	request_islegalaction, request_myindex, request_card, request_iseliminated, \
	request_discards, request_score, new_game, Card
from random_agent import RandomAgent
import tensorflow as tf
import numpy as np
import math
import random
import sys
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
#TODO
#extension to be added:
#ability to import checkpoints and train from there

retrain = False
if '--retrain' in sys.argv:
	retrain = True
else:
	print('Warning no retrain flag specified. Cannot overrwrite existing models')

Cards = []
for card in Card:
	Cards.append(card)

class Agent(metaclass=PlayerInterface):
	def __init__(self, model_index, model_ref):
		self.model_index = model_index
		self.model_ref = model_ref

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
		inputs = self.generate_inputs(drawn)
		logits = self.model_ref.call_slice(self.model_index, inputs).tolist()[0]
		indices = [x for _,x in sorted(zip(logits, list(range(len(logits)))), reverse=True)]
		for i in range(len(indices)):
			play, target, guess = self.parse_move(indices[i])
			if target >= self.num_players:
				continue
			if(request_islegalaction(self.socket, drawn, play, target, guess)):
				break
			if i == len(indices) - 1:
				print('no available legal move')
				sys.exit()
		send_action(self.socket, play, target, guess)

	def generate_inputs(self, drawn):
		rv = np.zeros([1,58],dtype=np.float32)
		rv[0][0] = self.num_players
		rv[0][1] = request_card(self.socket, self.index).value[0]
		rv[0][2] = drawn.value[0]
		for i in range(self.num_players - 1):
			player_index = i if i < self.index else i + 1
			if request_iseliminated(self.socket, player_index):
				rv[0][3+i] = -1
			else:
				card = request_card(self.socket, player_index)
				if card is not None:
					rv[0][3+i] = card.value[0]
				#0 default if unknown
		rv[0][6] = request_score(self.socket, self.index)
		for i in range(self.num_players - 1):
			player_index = i if i < self.index else i + 1
			rv[0][7+i] = request_score(self.socket, player_index)
		my_discards = request_discards(self.socket, self.index)
		for i in range(len(my_discards)):
			rv[0][10+i] = my_discards[i].value[0]
		for i in range(self.num_players - 1):
			player_index = i if i < self.index else i + 1
			discards = request_discards(self.socket,player_index)
			for j in range(len(discards)):
				rv[0][22 + i*12 +j] = discards[j].value[0]
		return rv

	def parse_move(self, move_num):
		card_rv = Card.PRINCESS
		target_rv = -1
		guess_rv = Card.GUARD
		if(move_num < 21):
			target_rv = move_num % 3
			if(target_rv >= self.index):
				target_rv += 1
			guess_rv = Cards[move_num//3+1]
			card_rv = Card.GUARD
		elif(move_num < 24):
			card_rv = Card.PRIEST
			target_rv = move_num - 21
			if(target_rv >=  self.index):
				target_rv += 1
		elif(move_num < 27):
			card_rv = Card.BARON
			target_rv = move_num - 24
			if(target_rv >= self.index):
				target_rv += 1
		elif(move_num == 27):
			card_rv = Card.HANDMAID
		elif(move_num < 32):
			card_rv = Card.PRINCE
			target_rv = move_num - 28
		elif(move_num < 35):
			card_rv = Card.KING
			target_rv = move_num - 32
			if(target_rv >= self.index):
				target_rv += 1
		else:
			card_rv = Card.COUNTESS
		return card_rv, target_rv, guess_rv



#hyperparamaters
hidden_layer_dim = 10
population = 24
#survival rate is a function
survival_init = 0.5
#uncertain if mutation_prob should be a function
mutation_init = 0.01
#definitely will be made into a function later
games_per_generation = 50

#other constants
best_agents_dir = 'best'
model_checkpoints_dir = 'checkpoints'
"""
structure of save files
models in best_agents_dir have root directory best_<generation_num>
models in model_checkpoints_dir have root directory model_<generation_num>
both structures are the same past that with an example structure being:
root-directory
	w1.np
	b1.np
	w2.np
	b2.np
	w3.np
	b3.np
the dimensions of these matrices differ in best_agents_dir vs model_checkpoints_dir
model_checkpoints_dir matrices are extended by the dimension: population
"""


"""
input neurons:
[1 x (num_players, hand_val, drawn, known_hands * 3, your_score, other_scores * 3,
your_discards * 12, other_discards * 3 * 12)]
ie [1 x 58]
output logits:
[1 x play_guard*21, play_priest*3, play_baron*3, play_handmaid*3, play_prince*4,
play_king*3, play_countess]
ie [1x36]
Arch of model:
hyper parameter: hidden_layer_dim = 100
Model kernel:
100*1(w1) x 1*58(input neurons) + 100*58 -> relu = 100*70(result1)
100*58(result1) x 58*36(w2) + 100*36(b2) -> relu = 100*36(result2)
1*100(w3) x 100*36(result2) + 1*36(b3) = 1*36(result3)
Graph arch:
[population*Model_kernel]
"""

class ModelSpace():
	def __init__(self, hidden_layer_dim=100,
		population=24,
		survival_init=0.5,
		mutation_init=0.01,
		games_per_generation=50):

		self.hidden_layer_dim = hidden_layer_dim
		self.population = population
		#useful to store sqrt
		self.population_sqrt = math.sqrt(population)
		self.survival_prob = survival_init
		self.mutation_prob = mutation_init
		self.games_per_generation = games_per_generation
		uniform_init = tf.random_uniform_initializer()
		self.input = tf.Variable(tf.zeros([1,58]))
		self.output = tf.Variable(tf.zeros([1,36]))
		self.w1 = tf.Variable(uniform_init([population,hidden_layer_dim,1]))
		self.b1 = tf.Variable(uniform_init([population,hidden_layer_dim,58]))
		self.w2 = tf.Variable(uniform_init([population,58,36]))
		self.b2 = tf.Variable(uniform_init([population, hidden_layer_dim, 36]))
		self.w3 = tf.Variable(uniform_init([population, 1, hidden_layer_dim]))
		self.b3 = tf.Variable(uniform_init([population, 1, 36]))
		self.w1_buff = [tf.Variable(tf.zeros(self.w1.shape[1:])) for _ in range(self.w1.shape[0])]
		self.w2_buff = [tf.Variable(tf.zeros(self.w2.shape[1:])) for _ in range(self.w2.shape[0])]
		self.w3_buff = [tf.Variable(tf.zeros(self.w3.shape[1:])) for _ in range(self.w3.shape[0])]
		self.b1_buff = [tf.Variable(tf.zeros(self.b1.shape[1:])) for _ in range(self.b1.shape[0])]
		self.b2_buff = [tf.Variable(tf.zeros(self.b2.shape[1:])) for _ in range(self.b2.shape[0])]
		self.b3_buff = [tf.Variable(tf.zeros(self.b3.shape[1:])) for _ in range(self.b3.shape[0])]
		self.train(50)

	@tf.function
	def cross_by_elem(self, rand_selection, parent1, parent2):
		return tf.where(rand_selection == 0, parent1, parent2)

	def cross(self, parent1, parent2):
		rand_selection = tf.random.uniform(parent1.shape, minval=0, maxval=2, dtype=tf.dtypes.int32)
		return self.cross_by_elem(rand_selection, parent1, parent2)

	@tf.function
	def mutate_by_elem(self, prob, mutate_vals, tensor):
		return tf.where(prob < self.mutation_prob, mutate_vals, tensor)

	def mutate(self, variable, lower_bound, upper_bound):
		probabilities = tf.random.uniform(variable.shape,dtype=tf.dtypes.float32)
		mutate_values = tf.random.uniform(variable.shape, minval=lower_bound, maxval=upper_bound,dtype=tf.dtypes.float32)
		return self.mutate_by_elem(probabilities, mutate_values, variable)

	def call_slice(self, index, input_vals):
		self.input.assign(tf.convert_to_tensor(input_vals))
		r1 = tf.nn.relu(tf.matmul(self.w1[index], self.input) + self.b1[index])
		r2 = tf.nn.relu(tf.matmul(r1, self.w2[index]) + self.b2[index])
		r3 = tf.matmul(self.w3[index], r2) + self.b3[index]
		return r3.numpy()

	def train(self, num_generations):
		scores = np.zeros(self.population)
		for generation in range(num_generations):
			print('building generation', generation)
			indices = [x for _,x in sorted(zip(list(scores), range(self.population)), reverse=True)]
			scores = np.zeros(self.population)
			#select
			for i in range(self.population):
				surviving_pop = math.ceil(self.survival_prob*self.population)
				parent1 = indices[i % surviving_pop]
				#likelier for higher performing parents
				parent2 = indices[int(random.random()*self.population_sqrt*4) % surviving_pop]
				#cross
				self.w1_buff[i].assign(self.cross(self.w1[parent1], self.w1[parent2]))
				self.w2_buff[i].assign(self.cross(self.w2[parent1], self.w2[parent2]))
				self.w3_buff[i].assign(self.cross(self.w3[parent1], self.w3[parent2]))
				self.b1_buff[i].assign(self.cross(self.b1[parent1], self.b1[parent2]))
				self.b2_buff[i].assign(self.cross(self.b2[parent1], self.b2[parent2]))
				self.b3_buff[i].assign(self.cross(self.b3[parent1], self.b3[parent2]))
			#axis 0 by default but more verbose
			self.w1.assign(tf.stack(self.w1_buff, axis=0))
			self.w2.assign(tf.stack(self.w2_buff, axis=0))
			self.w3.assign(tf.stack(self.w3_buff, axis=0))
			self.b1.assign(tf.stack(self.b1_buff, axis=0))
			self.b2.assign(tf.stack(self.b2_buff, axis=0))
			self.b3.assign(tf.stack(self.b3_buff, axis=0))
			print('\tselect, cross complete')
			#mutate
			self.mutate(self.w1, -0.05, 0.05)
			self.mutate(self.w2, -0.05, 0.05)
			self.mutate(self.w3, -0.05, 0.05)
			self.mutate(self.b1, -0.05, 0.05)
			self.mutate(self.b2, -0.05, 0.05)
			self.mutate(self.b3, -0.05, 0.05)
			print('\tmutate complete')
			agents = [Agent(i, self) for _ in range(self.population)]
			#2-4 players
			for num_players in range(2,5):
				for _ in range(math.ceil(self.games_per_generation / 3)):
					permutation = np.random.permutation(self.population)
					for i in range(0, population, num_players):
						next_agents = []
						for j in range(i, i + num_players):
							next_agents.append(agents[permutation[j]])
						score_buf = new_game(next_agents)
						winner = 0
						for j in range(num_players):
							if score_buf[winner] < score_buf[j]:
								winner = j
						#scaling scores so same amount of points are available
						#regardless of how many players or games
						scores[permutation[i + j]] += num_players
			print('\tfitness test complete')
			best_index = 0
			for i in range(population):
				if scores[i] > scores[best_index]:
					best_index = i
			twop_wr, threep_wr, fourp_wr = self.evaluate(agents[best_index])
			print('generation', generation, 'evaluated')
			print('\t2-player winrate: %d%%' % twop_wr)
			print('\t3-player winrate: %d%%' % threep_wr)
			print('\t4-player winrate: %d%%' % fourp_wr)
			self.save_checkpoint(generation)
			self.save_best(generation, best_index)

	def evaluate(self, best_agent):
		two_player_wr = 0
		three_player_wr = 0
		four_player_wr = 0
		agents = [best_agent, RandomAgent()]
		for _ in range(100):
			score_buf = new_game(agents)
			winner = 0
			for i in range(2):
				if score_buf[winner] < score_buf[i]:
					winner = i
			if winner == 0:
				two_player_wr += 1
		agents = [best_agent, RandomAgent(), RandomAgent()]
		for _ in range(100):
			score_buf = new_game(agents)
			winner = 0
			for i in range(3):
				if score_buf[winner] < score_buf[i]:
					winner = i
			if winner == 0:
				three_player_wr += 1
		agents = [best_agent, RandomAgent(), RandomAgent(), RandomAgent()]
		for _ in range(100):
			score_buf = new_game(agents)
			winner = 0
			for i in range(4):
				if score_buf[winner] < score_buf[i]:
					winner = i
			if winner == 0:
				four_player_wr += 1
		return two_player_wr, three_player_wr, four_player_wr

	def save_checkpoint(self, generation):
		parent_dir = os.path.join(os.getcwd(), model_checkpoints_dir)
		if  not os.path.isdir(parent_dir):
			if os.path.exists(parent_dir):
				os.remove(parent_dir)
			os.mkdir(parent_dir)
		root_dir = os.path.join(parent_dir, '%s_%d' % (model_checkpoints_dir, generation))
		if not os.path.exists(root_dir):
			os.mkdir(root_dir)
		elif retrain:
			if not os.path.isdir(root_dir):
				os.remove(root_dir)
			os.mkdir(parent_dir)
		else:
			print('Warning cannot save checkpoint')
			return
		self.w1.numpy().tofile(os.path.join(root_dir, 'w1.np'), ' ', '%f')
		self.w2.numpy().tofile(os.path.join(root_dir, 'w2.np'), ' ', '%f')
		self.w3.numpy().tofile(os.path.join(root_dir, 'w3.np'), ' ', '%f')
		self.b1.numpy().tofile(os.path.join(root_dir, 'b1.np'), ' ', '%f')
		self.b2.numpy().tofile(os.path.join(root_dir, 'b2.np'), ' ', '%f')
		self.b3.numpy().tofile(os.path.join(root_dir, 'b3.np'), ' ', '%f')

	def save_best(self, generation, index):
		parent_dir = os.path.join(os.getcwd(), best_agents_dir)
		if  not os.path.isdir(parent_dir):
			if os.path.exists(parent_dir):
				os.remove(parent_dir)
			os.mkdir(parent_dir)
		root_dir = os.path.join(parent_dir, '%s_%d' % (best_agents_dir, generation))
		if not os.path.exists(root_dir):
			os.mkdir(root_dir)
		elif retrain:
			if not os.path.isdir(root_dir):
				os.remove(root_dir)
			os.mkdir(parent_dir)
		else:
			print('Warning cannot save checkpoint')
			return
		self.w1[index].numpy().tofile(os.path.join(root_dir, 'w1.np'), ' ', '%f')
		self.w2[index].numpy().tofile(os.path.join(root_dir, 'w2.np'), ' ', '%f')
		self.w3[index].numpy().tofile(os.path.join(root_dir, 'w3.np'), ' ', '%f')
		self.b1[index].numpy().tofile(os.path.join(root_dir, 'b1.np'), ' ', '%f')
		self.b2[index].numpy().tofile(os.path.join(root_dir, 'b2.np'), ' ', '%f')
		self.b3[index].numpy().tofile(os.path.join(root_dir, 'b3.np'), ' ', '%f')


model = ModelSpace(hidden_layer_dim=hidden_layer_dim,
		population=population,
		survival_init=survival_init,
		mutation_init=mutation_init,
		games_per_generation=games_per_generation)

print('successfully trained')

