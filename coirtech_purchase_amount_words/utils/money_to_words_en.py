# -*- coding: utf-8 -*-
"""English amount in words for MXN and USD, without extra dependencies."""
from decimal import Decimal, ROUND_HALF_UP

_SMALL = (
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
    'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen',
    'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen',
)
_TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty',
         'seventy', 'eighty', 'ninety')
_SCALES = ('', 'thousand', 'million', 'billion', 'trillion',
           'quadrillion', 'quintillion', 'sextillion', 'septillion',
           'octillion', 'nonillion', 'decillion')


def _under_thousand(number):
    parts = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        parts.append(_SMALL[hundreds] + ' hundred')
    if remainder >= 20:
        tens, units = divmod(remainder, 10)
        parts.append(_TENS[tens] + ('-' + _SMALL[units] if units else ''))
    elif remainder:
        parts.append(_SMALL[remainder])
    return ' '.join(parts)


def _integer_to_words(number):
    if number == 0:
        return 'zero'
    chunks = []
    index = 0
    while number:
        number, chunk = divmod(number, 1000)
        if chunk:
            if index >= len(_SCALES):
                raise ValueError('Amount exceeds supported English number range')
            text = _under_thousand(chunk)
            if _SCALES[index]:
                text += ' ' + _SCALES[index]
            chunks.append(text)
        index += 1
    return ' '.join(reversed(chunks))


def amount_to_words_en(amount, currency_code):
    currency_code = (currency_code or '').upper()
    if currency_code not in ('MXN', 'USD'):
        return ''
    value = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    sign = 'minus ' if value < 0 else ''
    value = abs(value)
    integer = int(value)
    cents = int((value - Decimal(integer)) * 100)
    words = _integer_to_words(integer)
    if currency_code == 'MXN':
        unit = 'Mexican peso' if integer == 1 else 'Mexican pesos'
    else:
        unit = 'dollar' if integer == 1 else 'dollars'
    return f'{sign}{words} {unit} {cents:02d}/100 {currency_code}'.upper()
