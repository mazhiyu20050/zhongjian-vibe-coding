"""Explicit supported-person registry; never auto-load arbitrary corpus files."""
EXPANSION = {
    'confucius': ('孔子', ('孔子', '孔夫子', '孔丘', 'Confucius')),
    'laozi': ('老子', ('老子', '老聃', 'Laozi', 'Lao Tzu')),
    'zhuangzi': ('庄子', ('庄子', '庄周', '莊子', 'Zhuangzi')),
    'su-shi': ('苏轼', ('苏轼', '苏东坡', '蘇軾', 'Su Shi')),
    'lu-xun': ('鲁迅', ('鲁迅', '周树人', '魯迅', 'Lu Xun')),
    'nietzsche': ('尼采', ('尼采', 'Nietzsche')),
    'schopenhauer': ('叔本华', ('叔本华', '叔本華', 'Schopenhauer')),
}
MODERN_SLUGS = {'justin-sun','elon-musk'}
EXPANSION.update({
    'justin-sun': ('孙宇晨', ('孙宇晨','孫宇晨','Justin Sun')),
    'elon-musk': ('马斯克', ('马斯克','馬斯克','Elon Musk','Musk')),
})
BASE_ALIASES = {
    '王阳明': ('王阳明', '阳明', '王文成'),
    '毛泽东': ('毛泽东', '毛主席', '毛选'),
    '弗洛伊德': ('弗洛伊德', '佛洛伊德', 'Freud'),
}
PREFERENCE_PEOPLE = {
    'socrates':('苏格拉底',('苏格拉底','Socrates')),
    'plato':('柏拉图',('柏拉图','Plato')),
    'aristotle':('亚里士多德',('亚里士多德','Aristotle')),
    'einstein':('爱因斯坦',('爱因斯坦','Einstein')),
    'darwin':('达尔文',('达尔文','Darwin')),
    'buffett':('巴菲特',('巴菲特','Buffett')),
    'steve-jobs':('乔布斯',('乔布斯','Steve Jobs')),
    'adler':('阿德勒',('阿德勒','Adler')),
}

def named_people(question, available=None):
    aliases = {**BASE_ALIASES, **{person: names for person,names in {**EXPANSION,**PREFERENCE_PEOPLE}.values()}}
    text = question.casefold()
    return tuple(person for person,names in aliases.items()
                 if (available is None or person in available)
                 and any(name.casefold() in text for name in names))
