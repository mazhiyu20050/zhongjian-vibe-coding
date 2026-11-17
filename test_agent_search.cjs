const {test}=require('node:test');
const assert=require('node:assert/strict');
const match=require('./web/agents.js');
const people=require('./data/people/catalog.json');

test('contest profiles can be searched by name, alias and pinyin',()=>{
  for(const [query,person] of [['孔子','孔子'],['仲尼','孔子'],['王守仁','王阳明'],['Wáng yáng míng','王阳明'],
    ['laozi','老子'],['李耳','老子'],['王阳','王阳明']]){
    assert.equal(match(query,people)?.person,person,query);
  }
});

test('strong typos match but unknown or ambiguous names do not jump',()=>{
  for(const [query,person] of [['王扬明','王阳明'],['wangyanming','王阳明']]){
    assert.equal(match(query,people)?.person,person,query);
  }
  for(const query of ['陈独秀','胡适','诸葛亮','孔明','王','78o','波克']){
    assert.equal(match(query,people),null,query);
  }
  assert.equal(match('阿德拉',[{person:'阿德勒'},{person:'阿德莉'}]),null);
  assert.equal(match('苏试',[...people,{person:'苏试'}]).person,'苏试');
});

