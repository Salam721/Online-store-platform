"""
Unit tests for data_protection utilities:
  - PII masking (email, phone, address)
  - Log sanitization regex patterns
  - Tenant isolation helpers
"""
import sys, os, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

from data_protection import (
    mask_email, mask_phone, mask_address, mask_customer_data,
    sanitize_log_message, build_tenant_key, verify_tenant_access,
    get_region_for_customer,
)


class TestEmailMasking(unittest.TestCase):
    def test_standard_email_masked(self):
        result = mask_email('customer@example.com')
        self.assertNotIn('customer', result)
        self.assertIn('@', result)
        self.assertIn('***', result)

    def test_preserves_tld(self):
        result = mask_email('user@example.co.uk')
        self.assertTrue(result.endswith('.uk'))

    def test_single_char_username(self):
        result = mask_email('a@b.com')
        self.assertIn('***', result)

    def test_invalid_email_returns_placeholder(self):
        result = mask_email('not-an-email')
        self.assertEqual(result, 'invalid@example.com')

    def test_empty_email(self):
        result = mask_email('')
        self.assertEqual(result, 'invalid@example.com')


class TestPhoneMasking(unittest.TestCase):
    def test_10_digit_phone(self):
        result = mask_phone('5551234567')
        self.assertTrue(result.endswith('4567'))
        self.assertIn('***', result)

    def test_formatted_phone(self):
        result = mask_phone('555-123-4567')
        self.assertTrue(result.endswith('4567'))

    def test_international_phone(self):
        result = mask_phone('+15551234567')
        self.assertTrue(result.endswith('4567'))

    def test_empty_phone(self):
        result = mask_phone('')
        self.assertEqual(result, '***-***-****')


class TestAddressMasking(unittest.TestCase):
    def test_street_masked(self):
        result = mask_address({'street': '123 Main St', 'city': 'Seattle',
                                'state': 'WA', 'zip': '98101'})
        self.assertNotIn('123', result['street'])
        self.assertEqual(result['city'], 'Seattle')
        self.assertEqual(result['state'], 'WA')
        self.assertTrue(result['zip'].endswith('***'))

    def test_partial_address(self):
        result = mask_address({'city': 'Portland'})
        self.assertEqual(result['city'], 'Portland')
        self.assertEqual(result['state'], 'XX')


class TestCustomerDataMasking(unittest.TestCase):
    def test_full_customer_masked(self):
        customer = {'email': 'real@example.com', 'phone': '5551234567',
                    'name': 'John Smith',
                    'address': {'street': '123 Main', 'city': 'NY', 'state': 'NY', 'zip': '10001'}}
        masked = mask_customer_data(customer)
        self.assertNotIn('real@example.com', masked['email'])
        self.assertNotIn('5551234567', masked['phone'])
        self.assertNotIn('John Smith', masked['name'])
        self.assertNotIn('123 Main', masked['address']['street'])

    def test_original_not_mutated(self):
        customer = {'email': 'real@example.com', 'name': 'Alice'}
        mask_customer_data(customer)
        self.assertEqual(customer['email'], 'real@example.com')

    def test_missing_fields_handled(self):
        masked = mask_customer_data({'name': 'Bob'})
        self.assertNotIn('Bob', masked['name'])
        self.assertNotIn('email', masked)


class TestLogSanitization(unittest.TestCase):
    def test_email_replaced(self):
        result = sanitize_log_message('User customer@example.com logged in')
        self.assertNotIn('customer@example.com', result)
        self.assertIn('[EMAIL]', result)

    def test_phone_replaced(self):
        result = sanitize_log_message('Called 555-123-4567 for support')
        self.assertNotIn('555-123-4567', result)
        self.assertIn('[PHONE]', result)

    def test_credit_card_replaced(self):
        result = sanitize_log_message('Card 4111111111111111 processed')
        self.assertNotIn('4111111111111111', result)
        self.assertIn('[CREDIT_CARD]', result)

    def test_multiple_pii_types(self):
        result = sanitize_log_message(
            'user@test.com paid with 4111111111111111 phone 5551234567')
        self.assertIn('[EMAIL]',       result)
        self.assertIn('[CREDIT_CARD]', result)
        self.assertIn('[PHONE]',       result)

    def test_non_pii_unchanged(self):
        msg    = 'Order ord_123 processed successfully in 45ms'
        result = sanitize_log_message(msg)
        self.assertEqual(result, msg)


class TestTenantIsolation(unittest.TestCase):
    def test_partition_key_format(self):
        pk = build_tenant_key('tenant_abc', 'customer', 'cust_123')
        self.assertEqual(pk, 'tenant_abc#customer#cust_123')

    def test_verify_access_passes_for_correct_tenant(self):
        verify_tenant_access('tenant_abc', {'tenant_id': 'tenant_abc'})  # Should not raise

    def test_verify_access_raises_for_wrong_tenant(self):
        with self.assertRaises(ValueError):
            verify_tenant_access('tenant_abc', {'tenant_id': 'tenant_xyz'})

    def test_verify_access_raises_for_missing_tenant(self):
        with self.assertRaises(ValueError):
            verify_tenant_access('tenant_abc', {})


class TestDataResidency(unittest.TestCase):
    def test_eu_routes_to_ireland(self):
        self.assertEqual(get_region_for_customer('EU'), 'eu-west-1')

    def test_uk_routes_to_london(self):
        self.assertEqual(get_region_for_customer('UK'), 'eu-west-2')

    def test_us_routes_to_virginia(self):
        self.assertEqual(get_region_for_customer('US'), 'us-east-1')

    def test_unknown_defaults_to_us(self):
        self.assertEqual(get_region_for_customer('ZZ'), 'us-east-1')

    def test_case_insensitive(self):
        self.assertEqual(get_region_for_customer('eu'), 'eu-west-1')


if __name__ == '__main__':
    unittest.main()
