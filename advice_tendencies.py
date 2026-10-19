"""Model-estimated advice weights, not probabilities or historical measurements."""


def validate_options(value):
    if not isinstance(value,list) or not 2 <= len(value) <= 3:
        raise ValueError('invalid_advice_options')
    if any(not isinstance(s,str) or not 1 <= len(s.strip()) <= 4 for s in value):
        raise ValueError('invalid_advice_options')
    value=[s.strip() for s in value]
    if len(set(value)) != len(value):
        raise ValueError('duplicate_advice_options')
    return value


def validate_tendency(value, options, reason):
    if not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 120:
        raise ValueError('missing_tendency_reason')
    if value is None:
        return None
    if not isinstance(value,list) or len(value) != len(options):
        raise ValueError('invalid_tendency_shape')
    lookup={}
    for item in value:
        if not isinstance(item,dict) or set(item) != {'option','percent'}:
            raise ValueError('invalid_tendency_item')
        option,percent=item['option'],item['percent']
        if not isinstance(option,str) or option not in options or option in lookup:
            raise ValueError('unknown_tendency_option')
        if type(percent) is not int or not 0 <= percent <= 100 or percent % 10:
            raise ValueError('invalid_tendency_percent')
        lookup[option]=percent
    if sum(lookup.values()) != 100:
        raise ValueError('invalid_tendency_total')
    return [{'option':s,'percent':lookup[s]} for s in options]
