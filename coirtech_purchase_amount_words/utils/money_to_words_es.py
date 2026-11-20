# -*- coding: utf-8 -*-
"""Spanish (Mexico) currency text for MXN and USD, without third-party deps.

This module is intentionally independent of Odoo to make the grammar and
rounding testable. Monetary amounts are expected to have 2 decimal places.
"""

from decimal import Decimal, ROUND_HALF_UP

_UNITS = (
    'cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete',
    'ocho', 'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince',
    'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte',
    'veintiuno', 'veintidós', 'veintitrés', 'veinticuatro',
    'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho',
    'veintinueve',
)
_TENS = ('', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta',
         'setenta', 'ochenta', 'noventa')
_HUNDREDS = ('', 'ciento', 'doscientos', 'trescientos',
             'cuatrocientos', 'quinientos', 'seiscientos',
             'setecientos', 'ochocientos', 'novecientos')


def _under_hundred(number, apocope=False):
    """Return 0 <= number <= 99, shortening uno before masculine nouns."""
    if number < 30:
        if apocope and number == 1:
            return 'un'
        if apocope and number == 21:
            return 'veintiún'
        return _UNITS[number]
    tens, units = divmod(number, 10)
    result = _TENS[tens]
    if units:
        result += ' y ' + ('un' if units == 1 and apocope else _UNITS[units])
    return result


def _under_thousand(number, apocope=False):
    """Return 0 <= number < 1000."""
    if number == 0:
        return ''
    if number < 100:
        return _under_hundred(number, apocope)
    if number == 100:
        return 'cien'
    hundreds, remainder = divmod(number, 100)
    result = _HUNDREDS[hundreds]
    if remainder:
        result += ' ' + _under_hundred(remainder, apocope)
    return result


def _integer_to_words(number, apocope=False):
    """Convert a nonnegative integer to Spanish words (Spanish long scale)."""
    if number == 0:
        return 'cero'
    if number < 1000:
        return _under_thousand(number, apocope)
    if number < 1_000_000:
        thousands, remainder = divmod(number, 1000)
        thousands_words = 'mil' if thousands == 1 else (
            _under_thousand(thousands, apocope=True) + ' mil'
        )
        if remainder:
            thousands_words += ' ' + _under_thousand(remainder, apocope)
        return thousands_words
    if number < 1_000_000_000_000:
        millions, remainder = divmod(number, 1_000_000)
        millions_words = ('un millón' if millions == 1 else
                          _integer_to_words(millions, apocope=True) + ' millones')
        if remainder:
            millions_words += ' ' + _integer_to_words(remainder, apocope)
        return millions_words
    billions, remainder = divmod(number, 1_000_000_000_000)
    billions_words = ('un billón' if billions == 1 else
                      _integer_to_words(billions, apocope=True) + ' billones')
    if remainder:
        billions_words += ' ' + _integer_to_words(remainder, apocope)
    return billions_words


def amount_to_words_es(amount, currency_code):
    """Format amount in Spanish, such as 'CIEN PESOS 00/100 M.N.'.

    Returns an empty string if currency is not MXN or USD.
    The number is rounded to exactly 2 decimals for these currencies.
    """
    currency_code = (currency_code or '').upper()
    if currency_code not in ('MXN', 'USD'):
        return ''
    value = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    sign = 'menos ' if value < 0 else ''
    value = abs(value)
    integer = int(value)
    cents = int((value - Decimal(integer)) * 100)
    words = _integer_to_words(integer, apocope=True)
    singular = integer == 1
    if currency_code == 'MXN':
        unit = 'peso' if singular else 'pesos'
    else:
        unit = 'dólar' if singular else 'dólares'
    # Spanish requires 'de' after exact multiples of one million/billion.
    connector = ' de' if integer >= 1_000_000 and integer % 1_000_000 == 0 else ''
    # Always show cents as two digits over 100, including zero cents.
    # Show the requested currency suffix without changing the currency name.
    suffix = 'M.N.' if currency_code == 'MXN' else 'USD'
    return f'{sign}{words}{connector} {unit} {cents:02d}/100 {suffix}'.upper()
