# -*- coding: utf-8 -*-
"""Choose the language from the purchase order supplier's language code."""
from .money_to_words_es import amount_to_words_es
from .money_to_words_en import amount_to_words_en


def is_english(language):
    return (language or '').strip().replace('-', '_').lower().split('_', 1)[0] == 'en'


def amount_to_words(amount, currency_code, language=None):
    converter = amount_to_words_en if is_english(language) else amount_to_words_es
    return converter(amount, currency_code)


def amount_words_label(language=None):
    return 'Amount in words:' if is_english(language) else 'Importe con letra:'
