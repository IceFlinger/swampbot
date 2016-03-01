from jambot import botModule
import pycurl
import sys
import random
import re
import time
import string
import threading
from io import BytesIO
#Markov chain jambot module
#By ice at irc.kickinrad.tv

def mangle_line(line):
	links = re.findall(r'(https?://\S+)', line) 
	f = string.ascii_letters + string.digits + "():<>[].,!?/-^%$#@ "
	line = ' '.join(w for w in line.split() if w not in links) #Remove URLs
	line = ' '.join(w for w in line.split() if w[0] not in "[\"(") #Remove timestamp type stuff and quotes
	line = ' '.join(w for w in line.split() if w[-1] not in "\;\"%") #Remove broken words
	line = ' '.join(w for w in line.split() if not len(w)>26) #Remove long stuff
	line = ''.join(c for c in line if c in f) #Filter whole string with f chars
	return line

class moduleClass(botModule):
	dbload = True
	def on_start(self, c, e):
		self.replyrate = int(self.settings["replyrate"])
		self.learning = False
		self.cooldown = int(self.settings["cooldown"])
		self.lastmsg = 0
		self.maxchain = int(self.settings["maxchain"])
		if self.settings["learning"]=="True":
			self.learning = True
		self.nickreplyrate = int(self.settings["nickreplyrate"])

	def on_load_db(self):
		self.db_query("CREATE TABLE IF NOT EXISTS contexts (word1 text, word2 text DEFAULT '', freq int DEFAULT 0, UNIQUE(word1, word2))")
		self.db_commit()

	def build_sentence(self, c, e, msg):
		phrase = ""
		try:
			chainlength = 0
			exist_words = []
			for word in self.db_query("SELECT word1, word2 FROM contexts WHERE instr(LOWER(?), LOWER(word1)) > 0", [msg]):
				if (word[0].lower() in msg.lower().split()) and (word[0].lower()!=c.nickname.lower()) :
					exist_words.append(word)
			if exist_words:
				currentword = exist_words[random.randint(0,len(exist_words)-1)][0]
				while currentword != None:
					print(currentword, end=" ",flush=True)
					next_words = self.db_query("SELECT * FROM contexts WHERE LOWER(word1) LIKE LOWER(?) ORDER BY freq ASC", [currentword])
					total_contexts = 0
					for word in next_words:
						total_contexts += int(word[2])
					if total_contexts != 0:
						selection = random.randint(1, random.randint(1, total_contexts))
					else:
						selection = 0
					newword = None
					for word in next_words:
						selection -= int(word[2])
						if selection < 1 and newword == None:
							if word[1] != "":
								newword = word[1]
					if newword != currentword:
						if currentword=="#nick":
							currentword=e.source.nick
						phrase += currentword + " "
						chainlength += 1
					if chainlength > self.maxchain:
						newword = None
					currentword = newword
				print("")
		except:
			raise
		if phrase != "":
			self.send(e.target, phrase)
			self.lastmsg = time.time()

	def on_pubmsg(self, c, e):
		msg = mangle_line(e.arguments[0])
		own_nick = c.nickname
		lametrig = (len(msg.split())==2 and msg.split()[0]==own_nick) #People just baiting replies, don't wanna learn single word replies
		if self.learning and not lametrig:
			try:
				words = msg.split()
				for word1, word2 in zip(words[:-1], words[1:]):
					if word1.lower()==own_nick.lower(): #Replace own name with target's name in reply (thanks pyborg)
						word1="#nick"
					if word2.lower()==own_nick.lower():
						word2="#nick"
					self.db_query("INSERT OR IGNORE INTO contexts (word1, word2) VALUES (?, ?)", (word1, word2))
					self.db_query("UPDATE contexts SET freq = freq + 1 WHERE word1=? AND word2=?", (word1, word2))
				if len(words)!=0:
					if words[-1].lower()==own_nick.lower():
						words[-1]="#nick"
					self.db_query("INSERT OR IGNORE INTO contexts (word1) VALUES (?)", (words[-1], ))
					self.db_query("UPDATE contexts SET freq = freq + 1 WHERE word1=? AND word2 is ''", (words[-1], ))
				self.db_commit()
			except:
				raise
		roll = self.replyrate>random.randint(1,99)
		nickroll = self.nickreplyrate>random.randint(1,99)
		named = own_nick.lower() in msg.lower().split()
		cooled = time.time()>(self.lastmsg+self.cooldown)-1
		if (roll or (nickroll and named)) and cooled:
			t = threading.Thread(target=self.build_sentence, args=(c, e, msg))
			t.daemon = True
			t.start()

	def on_send(self, chan, msg, modulename):
		pass

	def on_event(self, c, e):
		pass

	def do_command(self, c, e, command, args, admin):
		if command=="feed" and admin and args:
			print("Downloading: " + args[0])
			self.send(e.target, "Downloading: " + args[0])
			textbytes = BytesIO()
			try:
				textconn = pycurl.Curl()
				textconn.setopt(textconn.URL, args[0])
				textconn.setopt(textconn.WRITEDATA, textbytes)
				textconn.perform()
				textconn.close()
				text = textbytes.getvalue().decode('iso-8859-1').split('\n')
				linecount = 0
				print("Learning...")
				self.send(e.target, "Learning")
				try:
					multi = 1
					if len(args)>1:
						multi = int(args[1])
					for line in text:
						line = mangle_line(line)
						words = line.split()
						for word1, word2 in zip(words[:-1], words[1:]):
							self.db_query("INSERT OR IGNORE INTO contexts (word1, word2) VALUES (?, ?)", (word1, word2))
							self.db_query("UPDATE contexts SET freq = freq + ? WHERE word1=? AND word2=?", (multi, word1, word2))
						if len(words)!=0:
							self.db_query("INSERT OR IGNORE INTO contexts (word1) VALUES (?)", (words[-1], ))
							self.db_query("UPDATE contexts SET freq = freq + ? WHERE word1=? AND word2 is ''", (multi, words[-1]))
						linecount += 1
						if ((linecount%1000)==0):
							print(str(linecount/1000).split(".")[0] + "k lines, ", end="" , flush=True)
				except:
					self.send(e.target, "Interrupted while learning from file (Something else accessing DB?)")
				try:
					self.db_commit()
					print("Learned from " + str(linecount) + " lines")
					self.send(e.target, "Learned from " + str(linecount) + " lines")
					print("Commited to DB")
				except:
					pass
			except:
				self.send(e.target, "Couldn't download file.")
		elif command=="words":
			words = self.db_query("SELECT COUNT(*) FROM (SELECT DISTINCT LOWER(word1) FROM contexts)")[0][0]
			contexts = self.db_query("SELECT sum(freq) FROM contexts")[0][0]
			self.send(e.target, "Currently have " + str(words) + " words and " + str(contexts)  + " contexts.")
		elif command=="known" and args:
			for word in args[:8]:
				contexts = contexts = self.db_query("SELECT sum(freq) FROM contexts WHERE word1=?", (word, ))[0][0]
				if contexts != None:
					self.send(e.target, "I know " + word + " in " + str(contexts)  + " contexts.")
				else:
					self.send(e.target, "I don't know " + word)
		elif command=="clean":
			contexts = self.db_query("SELECT sum(freq) FROM contexts")[0][0]
			self.send(e.target, "Used to have " + str(contexts)  + " contexts.")
			self.db_query("UPDATE contexts SET freq = cast((freq+1)/2 as int)")
			contexts = self.db_query("SELECT sum(freq) FROM contexts")[0][0]
			self.db_commit()
			self.send(e.target, "Now have " + str(contexts)  + " contexts.")

	def on_privmsg(self, c, e):
		pass

	def shutdown(self):
		pass
