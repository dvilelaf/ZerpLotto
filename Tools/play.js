'use strict';
const RippleAPI = require('ripple-lib').RippleAPI;
var config = require('../configTest.json');
var accounts = require('../testAccounts.json');

// Instantiate Ripple API
const api = new RippleAPI({
  server: "wss://s.altnet.rippletest.net:51233"
});

// Run
run();

// Sends XRP payments ---------------------------------------------------------
async function sendXRP(sender, secret, amount, fee, destination, memo, tag) {

  // Update amount
  amount = (Math.round( (amount - fee) * 1e6) / 1e6).toString();

  // Build payment
  const payment = {
    source: {
      address: sender,
      maxAmount: {
        value: amount,
        currency: 'XRP'
      }
    },
    destination: {
      address: destination,
      amount: {
        value: amount,
        currency: 'XRP'
      }
    },
    memos: [
      {
        data: memo,
        format: 'text/plain'
      }
    ]
  };

  if (tag != null) {
    payment.destination.tag = tag;
  }

  // Build instuctions
  const instructions = {
    maxLedgerVersionOffset: 5
  };

  console.log('Sending ' + amount + ' XRP to ' + destination);

  try {
    // Prepare the payment
    const preparedTX = await api.preparePayment(sender, payment, instructions);

    // Sign the payment
    const signedTX = api.sign(preparedTX.txJSON, secret);

    // Submit the payment
    const result = await api.submit(signedTX['signedTransaction']);

    // Return TX hash on successful TX
    if ('resultCode' in result && result['resultCode'] == 'tesSUCCESS') {
      return signedTX.id;
    } else {
      return null;
    }

  } catch (e) {
    console.error(e.message);
    process.exit(-1);
  }
}

// Main function --------------------------------------------------------------
function run() {

  var transactions = [];

  for (var i = 0; i < 100; i++) {

    var sender = accounts['accounts'][Math.floor(Math.random()*accounts['accounts'].length)];

    var prizes = [100, 1000]
    var tags = [100, 1000]

    let prize = prizes[Math.floor(Math.random() * prizes.length)];
    let tag = tags[Math.floor(Math.random() * tags.length)];
    let amount = prize * config.parameters.maxParticipationRatio * (0.5 + Math.random() )

    transactions.push({'sender': sender.address,
                       'secret': sender.secret,
                       'amount': amount,
                       'destination': config.accounts.lotto.address,
                       'memo': 'playTest',
                       'hash': null,
                       'tag': tag});
  }

  // Connect to Ripple server
  api.connect().then(() => {
    return api.getFee();
  }).then(async fee => {

    for (var i in transactions) {
      // Process the transaction
      transactions[i]['hash'] = await sendXRP(transactions[i].sender,
                                              transactions[i].secret,
                                              transactions[i].amount,
                                              Number(fee),
                                              transactions[i].destination,
                                              transactions[i].memo,
                                              transactions[i].tag);
    }

  }).then(() => {
    return api.disconnect();
  }).catch(console.error);
}
