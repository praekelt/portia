import json

import dateutil.parser

from twisted.internet.protocol import Factory
from twisted.internet.defer import maybeDeferred
from twisted.protocols.basic import LineReceiver


class JsonProtocolException(Exception):
    def __init__(self, message, command, reference_id):
        super(JsonProtocolException, self).__init__(message)
        self.message = message
        self.command = command
        self.reference_id = reference_id


class JsonProtocol(LineReceiver):

    version = '0.1.0'

    def __init__(self, portia):
        self.portia = portia

    def valid_version(self, received_version):
        return received_version == self.version

    def lineReceived(self, line):
        d = maybeDeferred(self.parseLine, line)
        d.addErrback(self.error)

    def parseLine(self, line):
        data = json.loads(line)
        version = data.get('version')
        command = data.pop('cmd', None)
        reference_id = data.pop('id', None)
        if not self.valid_version(version):
            raise JsonProtocolException(
                'Protocol version mismatch. Expected: %s, got: %s.' % (
                    self.version, version),
                command=command,
                reference_id=reference_id)

        handler = getattr(self, 'handle_%s' % (command,), None)
        if not handler:
            raise JsonProtocolException(
                'Unsupported command: %s.' % (command,),
                command=command,
                reference_id=reference_id)

        d = handler(**data.get('request'))
        d.addCallback(self.reply, command, reference_id)
        return d

    def reply(self, data, cmd, reference_id):
        self.sendLine(json.dumps({
            'status': 'ok',
            'cmd': 'reply',
            'reference_cmd': cmd,
            'reference_id': reference_id,
            'version': self.version,
            'response': data,
        }))

    def error(self, failure):
        exc = failure.trap(JsonProtocolException)
        if exc == JsonProtocolException:
            command = failure.value.command
            reference_id = failure.value.reference_id
        else:
            command = None
            reference_id = None

        self.sendLine(json.dumps({
            'status': 'error',
            'reference_cmd': command,
            'reference_id': reference_id,
            'message': failure.getErrorMessage(),
            'version': self.version,
        }))

    def handle_get(self, msisdn):
        return self.portia.get_annotations(msisdn)

    def handle_annotate(self, msisdn, key, value, timestamp=None):
        ts = dateutil.parser.parse(timestamp) if timestamp else None
        return self.portia.annotate(msisdn, key, value, timestamp=ts)


class JsonProtocolFactory(Factory):
    protocol = JsonProtocol

    def __init__(self, portia):
        self.portia = portia

    def buildProtocol(self, *args):
        p = self.protocol(self.portia)
        p.factory = self
        return p