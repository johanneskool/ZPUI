from time import sleep
from threading import Event, Lock
from random import randint

from ui import Canvas, DialogBox, Menu, Listbox, PrettyPrinter, GraphicsPrinter
from helpers import ExitHelper, local_path_gen

menu_name = "Snake"

i = None #Input device
o = None #Output device

score = 0
snake = [(10, 10), (11, 10), (12, 10)]
lose = False
direction = "right"
applex = None
appley = None
restart = False
choice_ongoing = False
speed = 0.1
level = 2
hs_easy = 0
hs_normal = 0
hs_hard = 0

local_path = local_path_gen(__name__)

def restart_game():
	global snake, lose, direction, score
	snake = [(10, 10), (11, 10), (12, 10)]
	lose = False
	direction = "right"
	score = 0

def init_app(input, output):
	#Gets called when app is loaded
	global i, o, c
	i = input; o = output; c = Canvas(o)

def callback():
	#Gets called when app is selected from menu
	splash()
	load_scores()
	mc = [  ["Start", start_game],
		["Difficulty", change_difficulty],
		["Highscores", see_highscores]]
	Menu(mc, i, o, name="Snake game main menu").activate()

def change_difficulty():
	global speed, level
	lc = [["Too young to die", 1], ["Hurt me plenty", 2], ["Nightmare !", 3]]
	PrettyPrinter("Select your level of difficulty", i, o, 5)
	selected_level = Listbox(lc, i, o, name="Level").activate()
	# If user presses Left, Listbox returns None
	if selected_level:
		level = selected_level
		if level == 3:
			speed = 0.05

def load_scores():
	global hs_easy, hs_normal, hs_hard
	try:
		with open(local_path("highscore"), "r") as f:
			hs_easy, hs_normal, hs_hard = [int(x) for x in next(f).split()]
		print "success"
	except:
		hs_easy = 0
		hs_normal = 0
		hs_hard = 0

def save_scores():
	record = [hs_easy, hs_normal, hs_hard]
	with open(local_path("highscore"), 'w') as f:
		fic.write(" ".join([str(r) for r in record]))

def splash():
	GraphicsPrinter(local_path("snake.png"), i, o, 3)

def avancer():
	snake.remove(snake[0])
	if direction == "right":
		snake.append((snake[-1][0]+1, snake[-1][1]))
	elif direction == "left":
		snake.append((snake[-1][0]-1, snake[-1][1]))
	elif direction == "down":
		snake.append((snake[-1][0], snake[-1][1]+1))
	else:
		snake.append((snake[-1][0], snake[-1][1]-1))

def set_keymap():
	keymap = {"KEY_LEFT": lambda:make_a_move("left"),
			  "KEY_RIGHT": lambda:make_a_move("right"),
			  "KEY_UP": lambda:make_a_move("up"),
			  "KEY_DOWN": lambda:make_a_move("down"),
			  "KEY_ENTER": confirm_exit}
	i.stop_listen()
	i.set_keymap(keymap)
	i.listen()

def confirm_exit():
	global choice_ongoing, lose
	choice_ongoing = True
	choice = DialogBox("ync", i, o, message="Exit the game?").activate() #TODO : Maybe a clearer message ?
	if choice is True:		#Exit
		lose = True
	elif choice is False:	#Restart
		restart_game()
	choice_ongoing = False
	set_keymap()

def perdu():
	global lose
	for segment in snake:
		if not(0<segment[0]<128):
			lose = True
		if not(0<segment[1]<64):
			lose = True
	for segment in snake[:-1]:
		if snake[-1] == segment:
			lose = True

def eat():
	global snake, score, level
	for segment in snake:
		if level != 1:
			if (segment[0] == applex and segment[1] == appley):
				consume_apple()
		else :
			if (abs(segment[0] - applex) < 2 and abs(segment[1] - appley) < 2):
				# we increse the size of the apple
				consume_apple()

def consume_apple():
	eat_apple()
	liste = []
	liste.append(snake[0])
	liste.extend(snake)
	snake = liste
	score += 1

def eat_apple():
	global applex, appley
	applex = None; appley = None

def create_apple():
	global applex, appley
	applex = randint(5,128-5) #to limit the difficulty -> no apple to close to the border
	appley = randint(5,64-5)
	while (applex, appley) in snake:
		# Will regenerate the apple x and y until they're no longer one of the snake points
		# At some point, it *might* be close to impossible to generate a point, since the snake will be so long
		# TODO: think of how to work around that? Maybe limit the length and then increase the speed ?
		applex = randint(5,128-5)
		appley = randint(5,64-5)


def draw_field():
	c = Canvas(o)
	c.rectangle((0, 0, 127, 63))
	c.point(snake)
	if not(applex and appley):
		create_apple()
	if level == 1:		# We draw the apple
		c.point([(applex, appley-1),									# the leaf
			(applex-1, appley),(applex, appley),(applex+1, appley),	# the top half
			(applex-1, appley+1),(applex, appley+1),(applex+1, appley+1)]) # the lower half
	else:
		c.point((applex, appley))
	c.display() 		# Display the canvas on the screen

def start_game():
	global lose, snake, restart, choice_ongoing, speed
	restart_game()
	set_keymap()
	while(lose == False):
		while choice_ongoing == True:
			sleep(0.1)
		draw_field()
		avancer()
		eat()
		perdu()
		if restart == True:
			restart = False
			restart_game()
		sleep(speed)		# Control the speed of the snake
	check_highscore()
	c = Canvas(o)
	c.centered_text("Score : " + str(score))
	c.display()
	sleep(1)
	c = Canvas(o)
	c.centered_text("Bye !")
	c.display()
	sleep(0.5)


def check_highscore():
	record = [hs_easy, hs_normal, hs_hard]
	if score > record[level -1]:
		record[level -1] = score
		c = Canvas(o)
		c.centered_text("Highscore !")
		c.display()
		save_scores()
		sleep(0.5)

def make_a_move(key):
	global direction
	assert(key in ["up", "down", "left", "right"])
	if (direction == "up" and key == "down")
		or (direction == "down" and key == "up")
		or (direction == "left" and key == "right")
		or (direction == "right" and key == "left"):
		pass
	else:
		direction = key


