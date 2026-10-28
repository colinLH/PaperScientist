// A bit belongs to a record's position, never to its click order.
export const RECORD_SCORE = [null,
  ['Hiraeth','hiraeth'], ['Solace','solace'], ['With These Hands','with-these-hands'],
  ['Echoes Of Home','echoes-of-home'], ['Wildflowers','wildflowers'], ['Memories Of Stone','memories-of-stone'],
  ['Home Was You','home-was-you'], ['Aurora','aurora'], ['Born Of The Sky','born-of-the-sky'],
  ['Aphelion','aphelion'], ['Convergence','convergence'], ['Cirrus','cirrus'],
  ['In This Moment','in-this-moment'], ['Origami','origami'], ['Starfire','starfire']
].map((item,mask)=>item&&({mask,title:item[0],slug:item[1],url:`/intro-assets/audio/records/${String(mask).padStart(2,'0')}.opus`,page:`https://www.scottbuckley.com.au/library/${item[1]}/`}));
export const recordIndices=mask=>[0,1,2,3].filter(i=>mask&(1<<i));
export const toggleRecord=(mask,index)=>mask^(1<<index);
