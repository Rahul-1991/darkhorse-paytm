import pyodbc
import base64
import json
import requests
from paytmchecksum import PaytmChecksum
from flask import request, Flask, abort, jsonify
from datetime import datetime, timedelta


app = Flask(__name__)


class RazorPay:

    def __init__(self):
        self.BaseURL = "https://api.razorpay.com/v1"
        self.Username = ""
        self.Password = ""
        self.PaymentEndpoint = "/payment_links"

    def EncodeBase64Text(self, originalText):
        base64Bytes = originalText.encode('ascii')
        textBytes = base64.b64encode(base64Bytes)
        decodedText = textBytes.decode('ascii')
        return decodedText

    def GenerateHeaders(self):
        authHeader = "Basic " + self.EncodeBase64Text(self.Username + ":" + self.Password)
        return { 'Authorization' : authHeader, 'Content-type' : 'application/json' }

    def GetPayment(self, Count =100, SkipIds=0):
        params = {'count': Count, 'skip': SkipIds}
        endPoint = self.BaseURL + self.PaymentEndpoint
        response = requests.get(endPoint, headers=self.GenerateHeaders(), params = params)
        return response


class PayTM:

    def __init__(self):
        self.MerchantID = ""
        self.MerchantKey = ""


class Payments:

    def __init__(self):
        self.db_conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};'
          'Server=;'
          'Database=;'
          'Uid=;'
          'Pwd=;')

    def check_user_payment(self, mobile, email):
        with self.db_conn:
            userExist = None
            userAmount = None
            cursor = self.db_conn.cursor()
            cursor.execute('''EXEC [dbo].[CheckUserExist] ?,?''', (mobile, email))
            fetch_data = cursor.fetchone()
            if fetch_data is not None:
                userExist = True if fetch_data[0] == 1 else False
                userAmount = fetch_data[1]
            cursor.close()
            return {'userExist': userExist, 'userAmount': userAmount}

    def get_user_data(self, mobile, email):
        with self.db_conn:
            cursor = self.db_conn.cursor()
            if mobile:
                cursor.execute('''SELECT [UserMobile], [PaymentDate] FROM [dbo].[User] WHERE [UserMobile] = ?''', mobile)
                fetch_data = cursor.fetchone()
                result = {'paymentDate': fetch_data[1], 'mobile': fetch_data[0]}
            else:
                cursor.execute('''SELECT [UserEmailId], [PaymentDate] FROM [dbo].[User] WHERE [UserEmailId] = ?''', email)
                fetch_data = cursor.fetchone()
                result = {'paymentDate': fetch_data[1], 'email': fetch_data[0]}
            cursor.close()
            return result

    def PaymentsCheckForCodeAndDiscount(self, code):
        with self.db_conn:
            valueFetch = (False, 0)
            cursor = self.db_conn.cursor()
            cursor.execute('''SELECT [CodeDiscount] FROM [dbo].[DiscountCode] WHERE [CodeText] = ?''', (code,))
            fetch_data = cursor.fetchone()
            if fetch_data is not None:
                valueFetch = (True, fetch_data[0])
            cursor.close()
            return valueFetch


@app.route('/')
def index():
    return jsonify({'success': 'API is up and running'})


@app.route('/General/GetUserSubscriptionData', methods=['GET'])
def GetUserSubscriptionData():
    mobile = request.args.get('CustomerMobile') or ''
    email = request.args.get('CustomerEmail') or ''
    payments = Payments()
    result = payments.check_user_payment(mobile, email)
    if result.get('userExist'):
        userData = payments.get_user_data(mobile, email)
        if userData.get('paymentDate'):
            payment_date = (userData.get('paymentDate') + timedelta(days=365)).strftime('%d %b %Y')
            return {'subscriptionExpiry': payment_date, 'isActiveCustomer': True}
        else:
            if result.get('userAmount') in (10800, 15500):
                return {'subscriptionExpiry': '30 May 2023', 'isActiveCustomer': True}
            return {'subscriptionExpiry': '10 Nov 2022', 'isActiveCustomer': True}
    else:
        count = 100
        skipIds = 0
        razorPayClient = RazorPay()
        while True:
            response = razorPayClient.GetPayment(Count=count, SkipIds=skipIds)
            if response.status_code == 200:
                responseJSONData = response.json()
                if len(responseJSONData["payment_links"]) > 0:
                    for responseItem in responseJSONData.get("payment_links"):
                        if responseItem.get('status') == 'paid':
                            customer_data = responseItem.get('notes')
                            if customer_data.get('CustomerEmail') and customer_data.get('CustomerEmail') == email:
                                paid_date = (datetime.fromtimestamp(responseItem.get('created_at')) + timedelta(days=365)).strftime('%d %b %Y')
                                return {'subscriptionExpiry': paid_date, 'isActiveCustomer': True}
                            if customer_data.get('CustomerMobile') and customer_data.get('CustomerMobile') == mobile:
                                paid_date = (datetime.fromtimestamp(responseItem.get('created_at')) + timedelta(days=365)).strftime('%d %b %Y')
                                return {'subscriptionExpiry': paid_date, 'isActiveCustomer': True}
                    skipIds = skipIds + count
                else:
                    break
            else:
                abort(response.status_code)
        return {'subscriptionExpiry': '', 'isActiveCustomer': False}


@app.route('/Payments/PayTM/Payment', methods=['POST'])
def PaymentsPayTMPayment():
    data = json.loads(request.data)
    PayTMClient = PayTM()
    paymentAmount = data.get('PaymentAmount')
    if data.get('CustomerDiscountCode'):
        paymentsClient = Payments()
        (codeActive, codeDiscount) = paymentsClient.PaymentsCheckForCodeAndDiscount(data.get('CustomerDiscountCode'))
        if codeActive:
            paymentAmount = paymentAmount - codeDiscount
    paytmParams = dict()
    paytmParams["body"] = {
        "mid": PayTMClient.MerchantID,
        "linkType": "FIXED",
        "linkDescription": data.get('CustomerDiscountCode'),
        "linkName": data.get('CustomerDiscountCode'),
        "amount": paymentAmount,
        "statusCallbackUrl": "http://api.mf.darkhorsestocks.in/Payments/PayTM/PaymentStatus",
        "customerContact": {
            "customerName": data.get('CustomerName'),
            "customerEmail": data.get('CustomerEmail'),
            "customerMobile": data.get('CustomerMobile')
        }
    }
    checksum = PaytmChecksum.generateSignature(json.dumps(paytmParams["body"]), PayTMClient.MerchantKey)
    paytmParams["head"] = {
        "tokenType": "AES",
        "signature": checksum
    }
    post_data = json.dumps(paytmParams)
    # for Staging
    # url = "https://securegw-stage.paytm.in/link/create"

    # for Production
    url = "https://securegw.paytm.in/link/create"
    response = requests.post(url, data=post_data, headers={"Content-type": "application/json"}).json()
    return response


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
