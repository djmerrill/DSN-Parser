"""
DSN Parser.

Usage:
	dsn_parser.py <dsn_file>

"""

from docopt import docopt


class Node(object):
	def __init__(self, text='', parent=None, children=None, t_start=0, t_end=0):
		self.text = text
		self.t_start = t_start
		self.t_end = t_end
		self.parent = parent
		if self.parent is not None:
			self.parent.children.append(self)

		if children is None:
			self.children = []

	def add_c(self, c):
		self.text += c
		if self.parent is not None:
			
			self.parent.add_c(c)

	def keyword(self):
		if len(self.text) > 0:
			return self.text.split()[0].strip('()')
		else:
			return ''


def get_keywords(text):
	# find keywords
	splits = text.split('(')
	splits = [s.split() for s in splits]
	keywords = set()
	for s in splits:
		if len(s) > 0:
			keywords.add(s[0])

	keywords = list(keywords)
	keywords.sort()
	return keywords


def main(arguments):
	print(arguments)

	with open(arguments['<dsn_file>'], 'r') as f:
		text = f.read()

	node_stack = []
	nodes = []
	for i, c in enumerate(text):
		if c == '(':
			print(str(len(nodes)), 'New node:', text[i:i+15].strip())
			if len(node_stack) > 0:
				node_stack.append(Node(parent=node_stack[-1]))
			else:
				node_stack.append(Node())
			node_stack[-1].t_start = i
			nodes.append(node_stack[-1])
		elif c == ')':
			node_stack[-1].t_end = i+1
			node_stack.pop()

	node_types = {}
	for n in nodes:
		n.text = text[n.t_start:n.t_end]
		print(n.keyword(), n.text)
		try:
			node_types[n.keyword()].append(n)
		except KeyError:
			node_types[n.keyword()] = [n]
	

	for n in node_types['component']:
		print(n.text
			)


if __name__ == "__main__":
	arguments = docopt(__doc__, version='DSN Parser 0.1')
	main(arguments)


