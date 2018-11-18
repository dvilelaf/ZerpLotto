'use strict';
const RippleAPI = require('ripple-lib').RippleAPI;
const sqlite3 = require('sqlite3').verbose();

// Check arguments and load configuration
if (process.argv.length == 3 && process.argv[2] == '--testing=False') {
  var config = require('./config.json');
} else {
  var config = require('./configTest.json');
}
const sender = config.accounts.lotto.address;
const secret = config.accounts.lotto.secret;

// Instantiate Ripple API
const api = new RippleAPI({
  server: config.parameters.connection
});

// Run
try {
  run();
} catch (e) {
  console.error(e.message);
  process.exit(-1);
}

// Sends XRP payments ---------------------------------------------------------
async function sendXRP(amount, fee, destination, memo) {

  // Update amount
  amount = (Math.floor( (amount - fee) * 1e6) / 1e6).toString();

  // Build payment
  const payment = {
    source: {
      address: sender,
      maxAmount: {
        value: amount,
        currency: 'XRP'
      }
      //tag: 0
    },
    destination: {
      address: destination,
      amount: {
        value: amount,
        currency: 'XRP'
      }
      //tag: 0
    },
    memos: [
      {
        data: memo,
        format: 'text/plain',
        //type:
    }
    ]
  };

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

  // Open database
  let db = new sqlite3.Database(config.parameters.database, sqlite3.OPEN_READWRITE, (err) => {
    if (err) {
        return console.error(err.message);
    }
  });

  // Get pending transacttions from database
  var sqlQuery = `SELECT id, destination, amount, memo, TXtype
                  FROM payment
                  WHERE TXid IS NULL`;

  var transactions = [];

  db.all(sqlQuery, [], (err, rows) => {
    if (err) {
        console.error(err.message);
    }
    rows.forEach(async (row) => {
      transactions.push({'id': row.id,
                         'type': row.TXtype,
                         'amount': row.amount,
                         'destination': row.destination,
                         'memo': row.memo,
                         'hash': null});
    })
  });


  // Connect to Ripple server
  api.connect().then(() => {
    return api.getFee();
  }).then(async fee => {

    for (var i in transactions) {
      // Process the transaction
      transactions[i]['hash'] = await sendXRP(transactions[i].amount,
                                              Number(fee),
                                              transactions[i].destination,
                                              transactions[i].memo);
    }

  }).then(() => {
    return api.disconnect();
  }).then(() => {

    // Update the database
    for (let i in transactions) {
      var status = '';

      if (transactions[i]['hash'] != null) {
        status = 'SUCCESS_NOT_FINAL';
      } else {
        status = 'ERROR';
      }

      sqlQuery = `UPDATE payment
                  SET TXid = ?, status = ?
                  WHERE id = ?`;

      const data = [transactions[i]['hash'], status, transactions[i]['id']];

      db.run(sqlQuery, data, (err) => {
        if (err) {
            return console.error(err.message);
        }
        console.log('Updated payment with id = ' + transactions[i]['id'] + ' => ' + status + ' [' + transactions[i]['type'] + ']');
      });
    }

    // Close the database
    db.close((err) => {
      if (err) {
          return console.error(err.message);
      }
    });

  }).catch(console.error);
}