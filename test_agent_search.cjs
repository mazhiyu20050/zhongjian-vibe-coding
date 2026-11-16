const {test}=require('node:test');
const assert=require('node:assert/strict');
const match=require('./web/agents.js');
const people=require('./data/people/catalog.json');

test('exact names, aliases, pinyin and compact pinyin are searchable',()=>{
  for(const [query,person] of [['乔布斯','乔布斯'],['王守仁','王阳明'],['Wáng yáng míng','王阳明'],
    ['sugeladi','苏格拉底'],['Steve Jobs','乔布斯'],['王阳','王阳明']]){
    assert.equal(match(query,people)?.person,person,query);
  }
});

test('correct strong typos without jumping for an unknown or ambiguous person',()=>{
  for(const [query,person] of [['王扬明','王阳明'],['弗络伊得','弗洛伊德'],['wangyanming','王阳明'],['苏试','苏轼'],['老紫','老子']]){
    assert.equal(match(query,people)?.person,person,query);
  }
  for(const query of ['陈独秀','胡适','诸葛亮','孔明','王','78o','波克']){
    assert.equal(match(query,people),null,query);
  }
  assert.equal(match('阿德拉',[{person:'阿德勒'},{person:'阿德莉'}]),null);
  assert.equal(match('苏试',[...people,{person:'苏试'}]).person,'苏试');
});
