import asyncio
import websockets
import json


class Ledger:

    def __init__(self, address):
        self.address = address
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.connect())


    async def connect(self):
        self.websocket = await websockets.connect(self.address, ssl=True)


    async def send(self, data):
        await self.websocket.send(json.dumps(data))
        response = json.loads(await self.websocket.recv())
        return response


    def get(self, data):
        data = self.loop.run_until_complete(self.send(data))

        if 'status' in data and data['status'] == 'success':
            return data['result']
        else:
            return None


    def getAccountInfo(self, address):
        data = {
                "id": 1,
                "command": "account_info",
                "account": address
        }

        return self.get(data)


    def getAccountTransactions(self, address, ledger_index_min=-1):

        transactions = []
        index_min = ledger_index_min

        while True:
            
            data = {
                    "id": 1,
                    "command": "account_tx",
                    "account": address,
                    "ledger_index_min": index_min,
                    "ledger_index_max": -1,
                    "binary": False,
                    "count": False,
                    "limit": 100,
                    "forward": True
            }

            result = self.get(data)['transactions']

            if result:

                if len(transactions) > 0:

                    # Delete duplicated txs
                    j = 0
                    for i in range(len(result)):
                        if result[i]['tx']['hash'] == transactions[-1]['tx']['hash']:
                            j = i + 1
                            break

                    result = result[j:]

                    if not result:
                        break

                # Add next txs batch
                transactions.extend(result)
                index_min = result[-1]['tx']['ledger_index']

            else:
                break

        return transactions


    def getTransaction(self, TXid):
        data = {
                "id": 1,
                "command": "tx",
                "transaction": TXid
        }

        return self.get(data)