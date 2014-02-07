import functools
import time
import logging
import irc.client
import urllib.request, urllib.parse
import sys

log = logging.getLogger('utils')

DEFAULT_THROTTLE = 15

class throttle(object):
	"""Prevent a function from being called more often than once per period

	Usage:
	@throttle([period])
	def func(...):
		...

	@throttle([period], notify=True)
	def func(self, conn, event, ...):
		...

	When called within the throttle period, the last return value is returned,
	akin to memoisation (but ignoring parameter values)
	"""
	def __init__(self, period=DEFAULT_THROTTLE, notify=False):
		self.period = period
		self.notify = notify
		self.lastrun = None
		self.lastreturn = None

	def __call__(self, func):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			if self.lastrun is None or time.time() - self.lastrun >= self.period:
				self.lastreturn = func(*args, **kwargs)
				self.lastrun = time.time()
				return self.lastreturn
			else:
				log.info("Skipping %s due to throttling" % func.__name__)
				if self.notify:
					conn = args[1]
					event = args[2]
					source = irc.client.NickMask(event.source)
					if irc.client.is_channel(event.target):
						respond_to = event.target
					else:
						respond_to = source.nick
					conn.privmsg(respond_to, "%s: A similar command has been registered recently" % source.nick)
				return self.lastreturn
		# Copy this method across so it can be accessed on the wrapped function
		wrapper.reset_throttle = self.reset_throttle
		return wrapper

	def reset_throttle(self):
		self.lastrun = None
		self.lastreturn = None

def mod_only(func):
	"""Prevent an event-handler function from being called by non-moderators

	Usage:
	@mod_only
	def on_event(self, conn, event, ...):
		...
	"""

	# Only complain about non-mods with throttle
	# but allow the command itself to be run without throttling
	@throttle()
	def mod_complaint(conn, event):
		source = irc.client.NickMask(event.source)
		if irc.client.is_channel(event.target):
			respond_to = event.target
		else:
			respond_to = source.nick
		conn.privmsg(respond_to, "%s: That is a mod-only command" % source.nick)

	@functools.wraps(func)
	def wrapper(self, conn, event, *args, **kwargs):
		if self.is_mod(event):
			return func(self, conn, event, *args, **kwargs)
		else:
			log.info("Refusing %s due to not-a-mod" % func.__name__)
			mod_complaint(conn, event)
			return None
	return wrapper

def log_errors(func):
	"""Log any errors thrown by a function"""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except:
			log.exception("Exception in " + func.__name__)
			raise
	return wrapper

def swallow_errors(func):
	"""Log and absorb any errors thrown by a function"""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except:
			log.exception("Exception in " + func.__name__)
			return None
	return wrapper

def http_request(url, data=None, method='GET', maxtries=3, **kwargs):
	"""Download a webpage, with retries on failure."""
	if data:
		if isinstance(data, dict):
			data = urllib.parse.urlencode(data)
		if method == 'GET':
			url = '%s?%s' % (url, data)
			args = (url,)
		else:
			args = (url, data.encode("utf-8"))
	else:
		args = (url,)

	firstex = None
	while True:
		try:
			return urllib.request.urlopen(*args, **kwargs).read().decode("utf-8")
		except Exception as e:
			maxtries -= 1
			if firstex is None:
				firstex = e
			if maxtries > 0:
				log.info("Downloading %s failed: %s, retrying..." % (url, e))
			else:
				break
	raise firstex

def nice_duration(duration):
	"""Convert a duration in seconds to a human-readable duration"""
	if duration < 0:
		return "-" + nice_duration(-duration)
	if duration < 60:
		return "%ds" % duration
	duration //= 60
	if duration < 60:
		return "%dm" % duration
	hours, minutes = divmod(duration, 60)
	if hours < 24:
		return "%d:%02d" % (hours, minutes)
	days, hours = divmod(hours, 24)
	return "%dd, %d:%02d" % (days, hours, minutes)