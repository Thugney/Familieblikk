"""Authentication work bounds against synthetic PostgreSQL state only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
from threading import Barrier, Event
import time
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from budget import identity
from budget.models import LoginCode, LoginRequest, PasswordAttempt
from budget.tests.test_preregistered_auth import PASSWORD, binding


class PasswordWorkBudgetTests(TestCase):
    def setUp(self):
        self.member, _ = identity.provision_owner(binding(), PASSWORD, 'Synthetic family')
        self.email = self.member.user.email
        self.ip = '192.0.2.8'

    def request(self):
        request = RequestFactory().post('/passord/')
        request.session = {}
        return request

    def test_successful_hashes_consume_email_work_budget_and_then_skip_hashing(self):
        with patch.object(identity, 'PASSWORD_WORK_EMAIL_LIMIT', 2), patch('budget.identity.login'):
            for _ in range(2):
                self.assertEqual(identity.password_login(self.request(), self.email, PASSWORD, self.ip).pk, self.member.user_id)
            self.assertEqual(PasswordAttempt.objects.filter(email_digest=identity.digest('password-work-email:' + self.email)).count(), 2)
            self.assertFalse(PasswordAttempt.objects.filter(email_digest=identity.digest('password-email:' + self.email)).exists())
            with patch.object(get_user_model(), 'check_password') as check, patch('django.contrib.auth.hashers.make_password') as dummy:
                with self.assertRaisesMessage(ValidationError, identity.LOGIN_ERROR):
                    identity.password_login(self.request(), self.email, PASSWORD, self.ip)
                check.assert_not_called()
                dummy.assert_not_called()

    def test_shared_ip_work_budget_applies_across_addresses_before_hashing(self):
        PasswordAttempt.objects.bulk_create([
            PasswordAttempt(email_digest=identity.digest(f'password-work-email:other{n}@example.test'),
                            ip_digest=identity.digest('password-work-ip:' + self.ip), attempted_at=timezone.now())
            for n in range(identity.PASSWORD_WORK_IP_LIMIT)
        ])
        with patch.object(get_user_model(), 'check_password') as check, patch('django.contrib.auth.hashers.make_password') as dummy:
            with self.assertRaisesMessage(ValidationError, identity.LOGIN_ERROR):
                identity.password_login(self.request(), self.email, PASSWORD, self.ip)
            check.assert_not_called()
            dummy.assert_not_called()

    def test_failure_budget_stays_five_and_does_not_count_successes(self):
        with patch('budget.identity.login'), patch.object(get_user_model(), 'check_password', return_value=True):
            identity.password_login(self.request(), self.email, PASSWORD, self.ip)
        with patch.object(get_user_model(), 'check_password', return_value=False) as check:
            for _ in range(6):
                with self.assertRaisesMessage(ValidationError, identity.LOGIN_ERROR):
                    identity.password_login(self.request(), self.email, 'wrong-password', self.ip)
            self.assertEqual(check.call_count, 5)
        self.assertEqual(PasswordAttempt.objects.filter(email_digest=identity.digest('password-email:' + self.email)).count(), 5)
        self.assertEqual(PasswordAttempt.objects.filter(email_digest=identity.digest('password-work-email:' + self.email)).count(), 6)

    def test_expired_work_records_do_not_block_valid_login(self):
        PasswordAttempt.objects.bulk_create([
            PasswordAttempt(email_digest=identity.digest('password-work-email:' + self.email),
                            ip_digest=identity.digest('password-work-ip:' + self.ip),
                            attempted_at=timezone.now() - timedelta(minutes=16))
            for _ in range(identity.PASSWORD_WORK_EMAIL_LIMIT)
        ])
        with patch('budget.identity.login'):
            self.assertEqual(identity.password_login(self.request(), self.email, PASSWORD, self.ip).pk, self.member.user_id)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationLockTests(TransactionTestCase):
    def test_concurrent_successes_cannot_exceed_shared_ip_work_budget(self):
        ip = '192.0.2.12'
        members = [identity.provision_owner(binding(f'person{n}@example.test'), PASSWORD, 'Synthetic family')[0]
                   for n in range(4)]
        PasswordAttempt.objects.bulk_create([
            PasswordAttempt(email_digest=identity.digest(f'password-work-email:previous{n}@example.test'),
                            ip_digest=identity.digest('password-work-ip:' + ip), attempted_at=timezone.now())
            for n in range(identity.PASSWORD_WORK_IP_LIMIT - 1)
        ])
        barrier = Barrier(len(members))
        def attempt(member):
            close_old_connections()
            try:
                request = RequestFactory().post('/passord/')
                request.session = {}
                barrier.wait(timeout=5)
                try:
                    identity.password_login(request, member.user.email, PASSWORD, ip)
                    return True
                except ValidationError as error:
                    self.assertEqual(error.messages, [identity.LOGIN_ERROR])
                    return False
            finally:
                close_old_connections()
        with patch.object(get_user_model(), 'check_password', return_value=True) as check, patch('budget.identity.login'):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(attempt, members))
            self.assertEqual(sum(results), 1)
            self.assertEqual(check.call_count, 1)
        self.assertEqual(PasswordAttempt.objects.filter(ip_digest=identity.digest('password-work-ip:' + ip)).count(), identity.PASSWORD_WORK_IP_LIMIT)

    def assert_contended_request_rejected(self, key, operation):
        ready, release = Event(), Event()
        def hold():
            close_old_connections()
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [key])
                    ready.set()
                    if not release.wait(10):
                        raise AssertionError('Synthetic lock holder was not released')
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold)
            try:
                self.assertTrue(ready.wait(5))
                started = time.monotonic()
                with patch.object(identity, 'AUTH_LOCK_WAIT_SECONDS', 0.08):
                    with self.assertRaisesMessage(ValidationError, identity.LOGIN_ERROR):
                        operation()
                self.assertLess(time.monotonic() - started, 1.0)
                # Rejection has not poisoned the connection or partially saved quota.
                self.assertFalse(PasswordAttempt.objects.exists())
                self.assertFalse(LoginRequest.objects.exists())
                self.assertFalse(LoginCode.objects.exists())
            finally:
                release.set()
                future.result(timeout=5)

    def test_password_contention_is_controlled_and_skips_hashing(self):
        email, ip = 'synthetic@example.test', '192.0.2.9'
        key = int(identity.digest('password-ip:' + ip)[:15], 16)
        with patch('django.contrib.auth.hashers.make_password') as dummy:
            self.assert_contended_request_rejected(key, lambda: identity.password_login(RequestFactory().post('/passord/'), email, PASSWORD, ip))
            dummy.assert_not_called()

    def test_code_ip_and_identity_contention_are_controlled_and_preserve_quota(self):
        email, ip = 'synthetic@example.test', '192.0.2.9'
        keys = [int(identity.digest('code-ip:' + ip)[:15], 16),
                int(hashlib.sha256(('identity-email:' + email).encode()).hexdigest()[:15], 16)]
        for key in keys:
            with self.subTest(key=key), patch('budget.identity.send_mail') as send:
                self.assert_contended_request_rejected(key, lambda: identity.send_code(email, ip))
                send.assert_not_called()
        identity.send_code(email, ip)
        self.assertEqual(LoginRequest.objects.count(), 1)


class MailTimeoutTests(TestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.test')
    def test_smtp_receives_finite_timeout_and_failed_send_rolls_back_quota(self):
        self.assertGreater(settings.EMAIL_TIMEOUT, 0)
        self.assertLessEqual(settings.EMAIL_TIMEOUT, 5)
        with patch('django.core.mail.backends.smtp.smtplib.SMTP', side_effect=TimeoutError('synthetic SMTP timeout')) as smtp:
            with self.assertRaises(TimeoutError):
                identity.send_code('synthetic@example.test', '192.0.2.10')
            self.assertEqual(smtp.call_args.kwargs['timeout'], settings.EMAIL_TIMEOUT)
        self.assertFalse(LoginRequest.objects.exists())
        self.assertFalse(LoginCode.objects.exists())
