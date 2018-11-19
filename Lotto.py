from peewee import *
from DBmodels import *
import datetime
import shutil
import json
import subprocess
import os
import sys
import random
import Ledger
from Notifications import Notifications, TelegramNotifier


class LottoException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class Lotto:

    def __init__(self, config):

        self.config = config

        # Initialize database
        db.init(self.config['parameters']['database'])
        db.create_tables([Prize, Fee, Donation, Devolution, Participant, Payment])
        db.close()

        # Instantiate ledger and retrieve account info
        self.ledger = Ledger.Ledger(self.config['parameters']['connection'])
        self.accountInfo = self.ledger.getAccountInfo(self.config['accounts']['lotto']['address'])
        self.accountInfo['account_data']['Balance'] = int(self.accountInfo['account_data']['Balance']) / 1e6

        if not self.accountInfo:
            raise LottoException('Error retrieving account data from XRPL')

        # Update transactions
        self.getLastTransactions()


    def getLastProcessedLedger(self):

        # Load participants
        db.connect(reuse_if_open=True)
        participants = Participant.select().order_by(Participant.id)

        # Participant table is not empty: return last participant ledgerIndex
        if participants.count() > 0:

            lastProcessedLedger = participants[-1].ledgerIndex
            db.close()
            return lastProcessedLedger

        # Participant table is empty: use last prize's data
        else:

            prizes = Prize.select().order_by(Prize.id)

            # Some prize has been already delivered. Return last prize ledger
            if prizes.count() > 0:

                lastPrize = prizes[-1]
                lastProcessedLedger = lastPrize.lastIncludedLedger
                db.close()
                return lastProcessedLedger

            # No prizes delivered yet
            else:

                db.close()
                return -1


    def getLastTransactions(self):

        # Get transactions since the last included ledger
        lastProcessedLedger = self.getLastProcessedLedger()

        if (self.config['parameters']['startFromLedger'] != -1) and \
           (lastProcessedLedger < self.config['parameters']['startFromLedger']):
            lastProcessedLedger = self.config['parameters']['startFromLedger']

        self.transactions = self.ledger.getAccountTransactions(self.config['accounts']['lotto']['address'],
                                                               ledger_index_min = lastProcessedLedger)
        if not self.transactions:
            raise LottoException('No new transactions received')

        # Delete first TX (activation) if tx history starts from the beggining
        if lastProcessedLedger == -1:
            self.transactions.pop(0)

        # Delete TXs already processed in the last prize
        # This prevents for txs included in the same ledger that the last tx included in a prize being skipped
        # As we are including 'lastProcessedLedger' as our first ledger, some already processed txs must be deleted
        lastIncludedTXs = self.getParticipantTXsByPrizeID()

        if lastIncludedTXs:
            j = 0
            for i in range(len(self.transactions)):
                if self.transactions[i]['tx']['hash'] == lastIncludedTXs[-1]:
                    j = i + 1
                    break

            self.transactions = self.transactions[j:]


    def processReceivedTransactions(self):

        db.connect(reuse_if_open=True)

        for tx in self.transactions:

            tx = tx['tx']

            # Received txs only
            if tx['Destination'] == self.config['accounts']['lotto']['address']:

                # Select prize destination using tag
                if 'DestinationTag' in tx:

                    # Skip tx if its destination tag is one of the reserved ones
                    if tx['DestinationTag'] in self.config['parameters']['reservedTags']:
                        print('Skipping tx {} due to tag {}'.format(tx['hash'], tx['DestinationTag']))
                        continue

                    prize = tx['DestinationTag']

                    if not prize in self.config['parameters']['prizes']:
                        prize = self.config['parameters']['prizes'][-1]
                else:
                    prize = self.config['parameters']['prizes'][-1]

                # Calculate max allowed participation
                participationAmount = int(tx['Amount']) / 1e6
                maxParticipation = self.config['parameters']['maxParticipationRatio'] * prize

                # Make a devolution if the received amount exceeds max and has not been included yet in Devolution
                devolution = None

                if (participationAmount > maxParticipation) and \
                (not Devolution.select().where(Devolution.receivedTXid == tx['hash']).exists()):

                    memo = 'ZERPLOTTO.COM_DEVOLUTION::Received_TX={}'.format(tx['hash'])

                    payment = Payment(TXtype = 'DEVOLUTION',
                                      status = 'PENDING',
                                      destination = tx['Account'],
                                      amount = participationAmount - maxParticipation,
                                      memo = memo)

                    payment.save()

                    devolution = Devolution(amount = participationAmount - maxParticipation,
                                            destination = tx['Account'],
                                            receivedTXid = tx['hash'],
                                            paymentid = payment.id)

                    devolution.save()

                    print("Devolution created: {} to {} because of exceeded value [{}]".format(devolution.amount,
                                                                                      devolution.destination,
                                                                                      participationAmount))

                    participationAmount = maxParticipation

                # Add new participant if tx has not been included yet
                if not Participant.select().where(Participant.TXid == tx['hash']).exists():

                    date = datetime.datetime.utcfromtimestamp( 946684800 + int(tx['date']) ).strftime('%Y-%m-%d %H:%M:%S')

                    participant = Participant(address = tx['Account'],
                                              amount = participationAmount,
                                              prize = prize,
                                              TXid = tx['hash'],
                                              date = date,
                                              ledgerIndex = tx['ledger_index'])

                    participant.save()

                    print("Added participant tx {}".format(tx['hash']))

        db.close()


    def processPrizes(self):

        db.connect(reuse_if_open=True)

        # Check if there are pending payments
        pendingPayments = Payment.select().where(Payment.status == 'PENDING').exists()

        # Compile senders addresses and probabilities for every prize
        for prizeValue in self.config['parameters']['prizes']:

            allParticipantsProcessed = False

            # Loop while there are enough txs to fill prizes
            while not allParticipantsProcessed:

                participants = Participant.select().where(Participant.prize == prizeValue)
                nparticipants = len(participants)

                if nparticipants == 0:
                    break

                processedParticipants = 0

                selectedParticipants = []
                selectedAddresses = []
                selectedTXs = []
                selectedAmounts = []
                selectedBalance = 0
                lastIncludedLedger = 0

                for p in participants:

                    selectedParticipants.append(p.id)
                    selectedAddresses.append(p.address)
                    selectedTXs.append(p.TXid)
                    selectedAmounts.append(p.amount)
                    selectedBalance += p.amount
                    lastIncludedLedger = p.ledgerIndex
                    processedParticipants += 1
                    allParticipantsProcessed = (processedParticipants >= nparticipants)

                    if selectedBalance >= prizeValue:
                        break

                if selectedBalance >= (self.accountInfo['account_data']['Balance'] -
                                       self.config['parameters']['reservedXRP']):
                    raise LottoException('Insufficient funds')

                if selectedBalance >= prizeValue:

                    # Select a winner address
                    rng = random.SystemRandom()
                    selectedIndices = list(range(len(selectedAddresses)))
                    winnerIndex = rng.choices(selectedIndices, weights=selectedAmounts, k=1)[0]
                    winnerAddress = selectedAddresses[winnerIndex]
                    winnerTX = selectedTXs[winnerIndex]

                    # Calculate prize
                    feeAmount = self.config['parameters']['platformFeeRatio'] * selectedBalance
                    donationAmount = self.config['parameters']['donationFeeRatio'] * selectedBalance
                    prizeAmount = selectedBalance - feeAmount - donationAmount

                    # Truncate ammounts to 6 decimals
                    feeAmount = float( int(feeAmount * 1e6) / 1e6)
                    donationAmount = float( int(donationAmount * 1e6) / 1e6)
                    prizeAmount = float( int(prizeAmount * 1e6) / 1e6)

                    # Add prize to database
                    payment = Payment(TXtype = 'PRIZE',
                                      status = 'PENDING',
                                      destination = winnerAddress,
                                      amount = prizeAmount,
                                      memo = '')

                    payment.save()

                    prize = Prize(destination = winnerAddress,
                                  amount = prizeAmount,
                                  paymentid = payment.id,
                                  winnerTXid = winnerTX,
                                  participantTXids = str(selectedTXs)[1:-1].replace('\'','').replace(' ',''),
                                  lastIncludedLedger = lastIncludedLedger)
                    prize.save()

                    payment.memo = 'ZERPLOTTO.COM_PRIZE::Prize_id={}::First_included_TX={}::Last_included_TX={}::Winner_TX={}' \
                                   .format(prize.id, selectedTXs[0], selectedTXs[-1], winnerTX)

                    payment.save()

                    print('Prize {} prepared to be sent'.format(prize.id))

                    # Add fee to database
                    payment = Payment(TXtype = 'FEE',
                                      status = 'PENDING',
                                      destination = self.config['accounts']['fees']['address'],
                                      amount = feeAmount,
                                      memo = 'ZERPLOTTO.COM_FEE::Prize_id={}'.format(prize.id))

                    payment.save()

                    fee = Fee(destination = self.config['accounts']['fees']['address'],
                              amount = feeAmount,
                              paymentid = payment.id,
                              prizeid = prize.id)

                    fee.save()

                    print('Fee {} prepared to be sent'.format(fee.id))

                    # Add donation to database
                    donationAccount = rng.choices(list(self.config['accounts']['donations'].keys()), k=1)[0]

                    donationAddress = self.config['accounts']['donations'][donationAccount]['address']

                    payment = Payment(TXtype = 'DONATION',
                                      status = 'PENDING',
                                      destination = donationAddress,
                                      amount = donationAmount,
                                      memo = 'ZERPLOTTO.COM_DONATION::Prize_id={}'.format(prize.id))

                    payment.save()

                    donation = Donation(destination = donationAddress,
                                        amount = donationAmount,
                                        paymentid = payment.id,
                                        prizeid = prize.id)

                    donation.save()

                    print('Donation {} prepared to be sent'.format(donation.id))

                    # Update balance
                    self.accountInfo['account_data']['Balance'] -= selectedBalance

                    # Delete processed participations
                    Participant.delete().where(Participant.id.in_(selectedParticipants)).execute()

                    pendingPayments = True

        if not db.is_closed():
            try:
                db.close()
            except OperationalError as e:
                pass #FIXME: exception raised on close

        return pendingPayments


    def checkPayments(self):

        db.connect(reuse_if_open=True)

        print('Checking finality of payments results...')

        payments = Payment.select().where( (Payment.status == 'SUCCESS_NOT_FINAL') &
                                           (Payment.TXid.is_null(False)) )

        # Update payments with final transaction info
        # Amounts also must be updated to reflect fee substraction
        for payment in payments:

            tx = self.ledger.getTransaction(payment.TXid)

            if tx['validated'] == True:

                payment.status = 'SUCCESS_FINAL'
                payment.amount = int(tx['Amount']) / 1e6
                payment.ledgerIndex = tx['ledger_index']
                date = datetime.datetime.utcfromtimestamp(946684800 + int(tx['date'])).strftime('%Y-%m-%d %H:%M:%S')
                payment.date = date
                payment.save()
                print('Updated payment with id = {} => SUCCESS_FINAL [{}]'.format(payment.id, payment.TXtype))

                record = None

                if payment.TXtype == 'PRIZE':

                    record = Prize.select().where(Prize.paymentid == payment.id)[0]

                elif payment.TXtype == 'FEE':

                    record = Fee.select().where(Fee.paymentid == payment.id)[0]

                elif payment.TXtype == 'DONATION':

                    record = Donation.select().where(Donation.paymentid == payment.id)[0]

                elif payment.TXtype == 'DEVOLUTION':

                    record = Devolution.select().where(Devolution.paymentid == payment.id)[0]

                record.amount = payment.amount
                record.save()

                # Send notifications
                if self.config['parameters']['notify'] and payment.TXtype != 'DEVOLUTION':
                    Notifications.paymentNotify(payment, record, self.config)

            else:

                print('Error in payment with id = {} [{}]'.format(payment.id, payment.TXtype))

        db.close()


    def rebuildDBfromLedger(self):

        db.connect(reuse_if_open=True)

        # Reset tables
        Prize.delete().execute()
        Fee.delete().execute()
        Devolution.delete().execute()
        Participant.delete().execute()

        # Init prize TX ranges
        prizeTXranges = []

        for tx in self.transactions:

            tx = tx['tx']

            # Sent txs only
            if tx['Account'] == self.config['accounts']['lotto']['address'] and 'Memos' in tx:

                # Read the first memo and decode it
                memo = tx['Memos'][0]['Memo']['MemoData']
                memo = bytearray.fromhex(memo).decode()

                if 'ZERPLOTTO.COM' in memo:

                    status = 'SUCCESS_FINAL'
                    destination = tx['Destination']
                    amount = int(tx['Amount']) / 1e6
                    TXid = tx['hash']
                    ledgerIndex = tx['ledger_index']
                    date = datetime.datetime.utcfromtimestamp( 946684800 + int(tx['date']) ).strftime('%Y-%m-%d %H:%M:%S')

                    memoData = memo.split('::')

                    # Restore payment
                    payment = Payment(TXtype = '',
                                      status = 'SUCCESS_FINAL',
                                      destination = destination,
                                      amount = amount,
                                      TXid = TXid,
                                      ledgerIndex = ledgerIndex,
                                      date = date,
                                      memo = memo)

                    if '_PRIZE' in memo:

                        payment.TXtype = 'PRIZE'
                        payment.save()

                        prizeID = memoData[1].split('=')[1]
                        firstIncludedTX = memoData[2].split('=')[1]
                        lastIncludedTX = memoData[3].split('=')[1]
                        winnerTXid = memoData[4].split('=')[1]

                        lastIncludedLedger = self.ledger.getTransaction(lastIncludedTX)['ledger_index']

                        prize = Prize(destination = destination,
                                      amount = amount,
                                      paymentid = payment.id,
                                      winnerTXid = winnerTXid,
                                      participantTXids = '',
                                      lastIncludedLedger = lastIncludedLedger)
                        prize.save()

                        prizeTag = None
                        for prizeValue in self.config['parameters']['prizes']:
                            if round(amount / prizeValue) == 1:
                                prizeTag = prizeValue
                                break

                        prizeTXranges.append((prize.id, firstIncludedTX, lastIncludedTX, prizeTag))

                    elif '_FEE' in memo:

                        payment.TXtype = 'FEE'
                        payment.save()

                        prizeID = memoData[1].split('=')[1]

                        fee = Fee(destination = destination,
                                  amount = amount,
                                  paymentid = payment.id,
                                  prizeid = prizeID)

                        fee.save()

                    elif '_DONATION' in memo:

                        payment.TXtype = 'DONATION'
                        payment.save()

                        prizeID = memoData[1].split('=')[1]

                        donation = Donation(destination = destination,
                                            amount = amount,
                                            paymentid = payment.id,
                                            prizeid = prizeID)
                        donation.save()

                    elif '_DEVOLUTION' in memo:

                        payment.TXtype = 'DEVOLUTION'
                        payment.save()

                        receivedTX = memoData[1].split('=')[1]

                        devolution = Devolution(amount = amount,
                                                destination = destination,
                                                receivedTXid = tx['hash'],
                                                paymentid = payment.id)
                        devolution.save()


        for ptxr in prizeTXranges:

            prize = Prize.select().where(Prize.id == ptxr[0])[0]

            fromIndex = self.transactions.index(list(filter(lambda t: t['tx']['hash'] == ptxr[1], self.transactions))[0])
            toIndex =   self.transactions.index(list(filter(lambda t: t['tx']['hash'] == ptxr[2], self.transactions))[0])

            participantTXids = []

            for i in range(0, len(self.transactions)):

                if self.transactions[i]['tx']['hash'] == ptxr[1]:
                    fromIndex = i

                elif self.transactions[i]['tx']['hash'] == ptxr[2]:
                    toIndex = i

                if (fromIndex is not None) and (toIndex is not None):

                    for j in range(fromIndex, toIndex + 1):

                        if self.transactions[j]['tx']['Destination'] == self.config['accounts']['lotto']['address']:

                            if ('DestinationTag' in self.transactions[j]['tx'] 
                            and self.transactions[j]['tx']['DestinationTag'] == ptxr[3]) or \
                            ('DestinationTag' not in self.transactions[j]['tx'] 
                            and ptxr[3] == self.config['parameters']['prizes'][-1]):

                                participantTXids.append(self.transactions[j]['tx']['hash'])

                    prize.participantTXids = str(participantTXids)[1:-1].replace('\'','').replace(' ','')
                    prize.save()

                    break

        db.close()


    def getParticipantTXsByPrizeID(self, prizeID=-1):

        if prizeID == -1:

            prizes = Prize.select().order_by(Prize.id)

            if prizes.exists():

                return prizes[-1].participantTXids.replace(' ','').split(',')

            else:

                return None

        else:

            prize = Prize.select(Prize.participantTXids).where(Prize.id == prizeID)

            if prize.exists():
                return prize[0].participantTXids.replace(' ','').split(',')
            else:
                return None


    def update(self):
        print("Updating...")
        self.processReceivedTransactions()
        return self.processPrizes()


    def processPayments(self):

        print('Processing payments...')
        result = subprocess.run(['/usr/bin/node', './processPayments.js'],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

        print(result.stdout.decode("utf-8").replace('\\n', '\n'))
        print(result.stderr.decode("utf-8").replace('\\n', '\n'))

        if result.returncode != 0:
            raise LottoException('Error while processing payments')


    def backup(self):
        filename = 'XRPLotto-backup-{}.db'.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        shutil.copyfile(db.database, filename)


if __name__ == "__main__":

    testing = True

    print('Lotto execution started on {}'.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    config = None

    try:

        # Load configuration
        configFilePath = 'configTest.json' if testing else 'config.json'

        with open(configFilePath, 'r') as configFile:

            config = json.load(configFile) # TODO: validate json scheme

            # Check for lock file
            lockFileName = './ZerpLottoLock'

            if os.path.isfile(lockFileName):

                raise LottoException('ZerpLotto is locked')

            else:

                lock = open(lockFileName,'w')

            # Instantiate Lotto
            lotto = Lotto(config)

            # Update and process payments
            if lotto.update():

                lotto.processPayments()

            # Check payments    
            lotto.checkPayments()

    except Exception as e:

        print(e)
        TelegramNotifier.sendMessage('ZerpLotto Error: {}'.format(e), config)
        print("Lotto execution stopped")

    else:

        # Remove lock
        os.remove(lockFileName)

    finally:

        print('Lotto execution finished on {}'.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print('-------------------------------------------------------------------------------')
