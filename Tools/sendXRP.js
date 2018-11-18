'use strict';
const RippleAPI = require('ripple-lib').RippleAPI;

// Instantiate Ripple API
const api = new RippleAPI({
  server: "wss://s.altnet.rippletest.net:51233"
});

// Run
run(process.argv[2], process.argv[3], process.argv[4], process.argv[5]);

// Sends XRP payments ---------------------------------------------------------
async function sendXRP(sender, secret, amount, destination) {

  // Update amount
  amount = (Math.round( amount * 1e6) / 1e6).toString();

  // Build payment
  const payment = {
    source: {
      address: sender,
      maxAmount: {
        value: amount,
        currency: 'XRP'
      },
      tag: 0
    },
    destination: {
      address: destination,
      amount: {
        value: amount,
        currency: 'XRP'
      },
      tag: 0
    }
  };

  // Build instuctions
  const instructions = {
    maxLedgerVersionOffset: 5
  };

  console.log('Sending ' + amount + ' XRP to ' + destination);

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
      console.log(result);
      return null;
  }
}

// Main function --------------------------------------------------------------
function run(sender, secret, amount, destination) {

  // Connect to Ripple server
  api.connect().then(() => {
    return api.getFee();
  }).then(async fee => {

        var hash = await sendXRP(sender,
                                 secret,
                                 amount,
                                 destination);

        console.log(hash);

  }).then(() => {
    return api.disconnect();
  }).catch(console.error);
}
