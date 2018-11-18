from peewee import *

db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class Payment(BaseModel):
    id = PrimaryKeyField()
    TXtype = TextField()
    status = TextField()
    destination = TextField()
    amount = DoubleField()
    TXid = TextField(null = True)
    ledgerIndex = IntegerField(null = True)
    date = DateTimeField(null = True) # UTC timestamp
    memo = TextField()


class QueuedPayment(BaseModel):
    id = PrimaryKeyField()
    destination = TextField()
    amount = DoubleField()
    paymentid = IntegerField()


class Prize(QueuedPayment):
    winnerTXid = TextField()
    participantTXids = TextField()
    lastIncludedLedger = IntegerField()


class Fee(QueuedPayment):
    prizeid = IntegerField()


class Donation(QueuedPayment):
    prizeid = IntegerField()


class Devolution(QueuedPayment):
    receivedTXid = TextField()


class Participant(BaseModel):
    id = PrimaryKeyField()
    address = TextField()
    amount = DoubleField()
    prize = IntegerField()
    TXid = TextField()
    ledgerIndex = IntegerField(null = True)
    date = DateTimeField(null = True)