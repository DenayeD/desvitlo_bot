# Тест налаштувань для Telegram Stars
from test import PAYMENT_PROVIDER_TOKEN, CURRENCY, RGB_SUBSCRIPTION_PRICE

print('🔍 Перевірка налаштувань Telegram Stars:')
print(f'✅ PAYMENT_PROVIDER_TOKEN: "{PAYMENT_PROVIDER_TOKEN}" (має бути пустим)')
print(f'✅ CURRENCY: "{CURRENCY}" (має бути XTR)')
print(f'✅ RGB_SUBSCRIPTION_PRICE: {RGB_SUBSCRIPTION_PRICE} (ціна в зірках)')

# Перевірка коректності
errors = []
if PAYMENT_PROVIDER_TOKEN != '':
    errors.append('❌ PAYMENT_PROVIDER_TOKEN має бути пустим рядком')
if CURRENCY != 'XTR':
    errors.append('❌ CURRENCY має бути XTR')
if RGB_SUBSCRIPTION_PRICE <= 0:
    errors.append('❌ Ціна має бути більше 0')

if not errors:
    print()
    print('🎉 Всі налаштування правильні для Telegram Stars!')
    print('Тепер увімкніть платежі в BotFather та тестуйте.')
else:
    print()
    print('❌ Знайдені помилки:')
    for error in errors:
        print(f'  {error}')