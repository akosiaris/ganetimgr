#!/usr/bin/env python
"""beanstalkc - A beanstalkd Client Library for Python"""

__license__ = '''
Copyright (C) 2008-2010 Andreas Bolka

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

__version__ = '0.2.0'

import logging
import socket
import re


DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 11300
DEFAULT_PRIORITY = 2**31
DEFAULT_TTR = 120
DEFAULT_TIMEOUT = 1


class BeanstalkcException(Exception): pass
class UnexpectedResponse(BeanstalkcException): pass
class CommandFailed(BeanstalkcException): pass
class DeadlineSoon(BeanstalkcException): pass
class SocketError(BeanstalkcException): pass


class Connection(object):
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 connection_timeout=DEFAULT_TIMEOUT):
        self._socket = None
        self.host = host
        self.port = port
        self.connection_timeout = connection_timeout
        self.connect()

    def connect(self):
        """Connect to beanstalkd server, unless already connected."""
        if not self.closed:
            return
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.connection_timeout)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(None)
            self._socket_file = self._socket.makefile('rb')
        except socket.error, e:
            self._socket = None
            raise SocketError(e)

    def close(self):
        """Close connection to server, if it is open."""
        if self.closed:
            return
        try:
            self._socket.sendall('quit\r\n')
            self._socket.close()
        except socket.error:
            pass
        finally:
            self._socket = None

    @property
    def closed(self):
        return self._socket is None

    def _interact(self, command, expected_ok, expected_err=[], size_field=None):
        try:
            self._socket.sendall(command)
            status, results = self._read_response()
            if status in expected_ok:
                if size_field is not None:
                    results.append(self._read_body(int(results[size_field])))
                return results
            elif status in expected_err:
                raise CommandFailed(command.split()[0], status, results)
            else:
                raise UnexpectedResponse(command.split()[0], status, results)
        except socket.error, e:
            self.close()
            raise SocketError(e)

    def _read_response(self):
        line = self._socket_file.readline()
        if not line:
            raise socket.error('no data read')
        response = line.split()
        return response[0], response[1:]

    def _read_body(self, size):
        body = self._socket_file.read(size)
        self._socket_file.read(2) # trailing crlf
        if size > 0 and not body:
            raise socket.error('no data read')
        return body

    def _interact_value(self, command, expected_ok, expected_err=[]):
        return self._interact(command, expected_ok, expected_err)[0]

    def _interact_job(self, command, expected_ok, expected_err, reserved=True):
        jid, _, body = self._interact(command, expected_ok, expected_err,
                                      size_field=1)
        return Job(self, int(jid), body, reserved)

    def _interact_yaml_dict(self, command, expected_ok, expected_err=[]):
        _, body, = self._interact(command, expected_ok, expected_err,
                                  size_field=0)
        return parse_yaml_dict(body)

    def _interact_yaml_list(self, command, expected_ok, expected_err=[]):
        _, body, = self._interact(command, expected_ok, expected_err,
                                  size_field=0)
        return parse_yaml_list(body)

    def _interact_peek(self, command):
        try:
            return self._interact_job(command, ['FOUND'], ['NOT_FOUND'], False)
        except CommandFailed, (_, status, results):
            return None

    # -- public interface --

    def put(self, body, priority=DEFAULT_PRIORITY, delay=0, ttr=DEFAULT_TTR):
        """Put a job into the current tube. Returns job id."""
        assert isinstance(body, str), 'Job body must be a str instance'
        jid = self._interact_value(
                'put %d %d %d %d\r\n%s\r\n' %
                    (priority, delay, ttr, len(body), body),
                ['INSERTED', 'BURIED'], ['JOB_TOO_BIG'])
        return int(jid)

    def reserve(self, timeout=None):
        """Reserve a job from one of the watched tubes, with optional timeout in
        seconds. Returns a Job object, or None if the request times out."""
        if timeout is not None:
            command = 'reserve-with-timeout %d\r\n' % timeout
        else:
            command = 'reserve\r\n'
        try:
            return self._interact_job(command,
                                      ['RESERVED'],
                                      ['DEADLINE_SOON', 'TIMED_OUT'])
        except CommandFailed, (_, status, results):
            if status == 'TIMED_OUT':
                return None
            elif status == 'DEADLINE_SOON':
                raise DeadlineSoon(results)

    def kick(self, bound=1):
        """Kick at most bound jobs into the ready queue."""
        return int(self._interact_value('kick %d\r\n' % bound, ['KICKED']))

    def peek(self, jid):
        """Peek at a job. Returns a Job, or None."""
        return self._interact_peek('peek %d\r\n' % jid)

    def peek_ready(self):
        """Peek at next ready job. Returns a Job, or None."""
        return self._interact_peek('peek-ready\r\n')

    def peek_delayed(self):
        """Peek at next delayed job. Returns a Job, or None."""
        return self._interact_peek('peek-delayed\r\n')

    def peek_buried(self):
        """Peek at next buried job. Returns a Job, or None."""
        return self._interact_peek('peek-buried\r\n')

    def tubes(self):
        """Return a list of all existing tubes."""
        return self._interact_yaml_list('list-tubes\r\n', ['OK'])

    def using(self):
        """Return a list of all tubes currently being used."""
        return self._interact_value('list-tube-used\r\n', ['USING'])

    def use(self, name):
        """Use a given tube."""
        return self._interact_value('use %s\r\n' % name, ['USING'])

    def watching(self):
        """Return a list of all tubes being watched."""
        return self._interact_yaml_list('list-tubes-watched\r\n', ['OK'])

    def watch(self, name):
        """Watch a given tube."""
        return int(self._interact_value('watch %s\r\n' % name, ['WATCHING']))

    def ignore(self, name):
        """Stop watching a given tube."""
        try:
            return int(self._interact_value('ignore %s\r\n' % name,
                                            ['WATCHING'],
                                            ['NOT_IGNORED']))
        except CommandFailed:
            return 1

    def stats(self):
        """Return a dict of beanstalkd statistics."""
        return self._interact_yaml_dict('stats\r\n', ['OK'])

    def stats_tube(self, name):
        """Return a dict of stats about a given tube."""
        return self._interact_yaml_dict('stats-tube %s\r\n' % name,
                                        ['OK'],
                                        ['NOT_FOUND'])

    def pause_tube(self, name, delay):
        """Pause a tube for a given delay time, in seconds."""
        self._interact('pause-tube %s %d\r\n' %(name, delay),
                       ['PAUSED'],
                       ['NOT_FOUND'])

    # -- job interactors --

    def delete(self, jid):
        """Delete a job, by job id."""
        self._interact('delete %d\r\n' % jid, ['DELETED'], ['NOT_FOUND'])

    def release(self, jid, priority=DEFAULT_PRIORITY, delay=0):
        """Release a reserved job back into the ready queue."""
        self._interact('release %d %d %d\r\n' % (jid, priority, delay),
                       ['RELEASED', 'BURIED'],
                       ['NOT_FOUND'])

    def bury(self, jid, priority=DEFAULT_PRIORITY):
        """Bury a job, by job id."""
        self._interact('bury %d %d\r\n' % (jid, priority),
                       ['BURIED'],
                       ['NOT_FOUND'])

    def touch(self, jid):
        """Touch a job, by job id, requesting more time to work on a reserved
        job before it expires."""
        self._interact('touch %d\r\n' % jid, ['TOUCHED'], ['NOT_FOUND'])

    def stats_job(self, jid):
        """Return a dict of stats about a job, by job id."""
        return self._interact_yaml_dict('stats-job %d\r\n' % jid,
                                        ['OK'],
                                        ['NOT_FOUND'])


class Job(object):
    def __init__(self, conn, jid, body, reserved=True):
        self.conn = conn
        self.jid = jid
        self.body = body
        self.reserved = reserved

    def _priority(self):
        stats = self.stats()
        if isinstance(stats, dict):
            return stats['pri']
        return DEFAULT_PRIORITY

    # -- public interface --

    def delete(self):
        """Delete this job."""
        self.conn.delete(self.jid)
        self.reserved = False

    def release(self, priority=None, delay=0):
        """Release this job back into the ready queue."""
        if self.reserved:
            self.conn.release(self.jid, priority or self._priority(), delay)
            self.reserved = False

    def bury(self, priority=None):
        """Bury this job."""
        if self.reserved:
            self.conn.bury(self.jid, priority or self._priority())
            self.reserved = False

    def touch(self):
        """Touch this reserved job, requesting more time to work on it before it
        expires."""
        if self.reserved:
            self.conn.touch(self.jid)

    def stats(self):
        """Return a dict of stats about this job."""
        return self.conn.stats_job(self.jid)

def parse_yaml_dict(yaml):
    """Parse a YAML dict, in the form returned by beanstalkd."""
    dict = {}
    for m in re.finditer(r'^\s*([^:\s]+)\s*:\s*([^\s]*)$', yaml, re.M):
        key, val = m.group(1), m.group(2)
        # Check the type of the value, and parse it.
        if key == 'name' or key == 'tube' or key == 'version':
            dict[key] = val   # String, even if it looks like a number
        elif re.match(r'^(0|-?[1-9][0-9]*)$', val) is not None:
            dict[key] = int(val) # Integer value
        elif re.match(r'^(-?\d+(\.\d+)?(e[-+]?[1-9][0-9]*)?)$', val) is not None:
            dict[key] = float(val) # Float value
        else:
            dict[key] = val     # String value
    return dict

def parse_yaml_list(yaml):
    """Parse a YAML list, in the form returned by beanstalkd."""
    return re.findall(r'^- (.*)$', yaml, re.M)

if __name__ == '__main__':
    import doctest, os, signal
    try:
        pid = os.spawnlp(os.P_NOWAIT,
                         'beanstalkd',
                         'beanstalkd', '-l', '127.0.0.1', '-p', '14711')
        doctest.testfile('TUTORIAL.md', optionflags=doctest.ELLIPSIS)
        doctest.testfile('test/network.doctest', optionflags=doctest.ELLIPSIS)
    finally:
        os.kill(pid, signal.SIGTERM)
