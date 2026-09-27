"""Source-grounded incident briefs; publication times never become event times."""
import datetime as dt,re
from locations import STATES
TIME=re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|yesterday|tonight|last night|this morning|this afternoon|overnight|20\d{2}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,?\s+20\d{2})?|\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\b',re.I)

def format_summary(row):
 f=row['facts'];l=f['location'];counts=f['casualties'];text=row['title']+'. '+row.get('source_text',row.get('text',''))
 if row.get('ai_details',{}).get('time_reference'):when=row['ai_details']['time_reference']
 else:when=', '.join(dict.fromkeys(m.group(0) for m in TIME.finditer(text[:3000])))
 fragments=[]
 for key,verb in [('killed','killed'),('injured','injured')]:
  n=counts.get(key)
  if n is not None:fragments.append(('No people were' if n==0 else 'One person was' if n==1 else f'{n} people were')+' '+verb)
 if not fragments and counts.get('shot') is not None:
  n=counts['shot'];fragments=[('One person was' if n==1 else f'{n} people were')+' shot']
 statement=' and '.join([fragments[0]]+[v[0].lower()+v[1:] for v in fragments[1:]])+' in a gun violence incident' if fragments else 'A gun violence incident was reported'
 if when:statement+=' ('+when+'; as stated by the source)'
 parts=[]
 for value in [l.get('address') or l.get('street'),l.get('area'),l.get('city') or l.get('named_place'),l.get('county')]:
  if value and value.casefold() not in [p.casefold() for p in parts]:parts.append(value)
 if parts:statement+=' in '+', '.join(parts)
 if l.get('state'):statement+=' in '+STATES.get(l['state'],l['state'])
 if not l.get('state') and not parts:statement+='; the precise location remains unconfirmed'
 if not when:
  published=row.get('published_at')
  stamp=dt.datetime.fromtimestamp(published,dt.timezone.utc).strftime('%d %B %Y at %H:%M UTC') if published else None
  prefix=f"According to a report from {row.get('source','the source')} published on {stamp}, " if stamp else f"According to {row.get('source','the source')} (publication time unavailable), "
  statement=prefix+statement[0].lower()+statement[1:]
 statement+='.'
 updates=row.get('ai_details',{}).get('updates',[])
 if updates:statement+='\nReported update: '+' '.join(updates)
 if not row.get('source_text',row.get('text','')):statement+='\nHeadline only; article text is unavailable. Missing incident details have not been inferred.'
 return statement
