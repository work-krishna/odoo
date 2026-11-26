-- A copied database must not text real customers or spend the NestSMS wallet.
UPDATE res_company
   SET sms_nestsms_api_key = NULL;
