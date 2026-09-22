# slim.jq — projection presets piped into every read so raw API envelopes never
# reach the model context.  Usage:
#   pj_req GET /issues?...        | jq -f assets/slim.jq --arg view issue
#   pj_req GET /issues/{id}       | jq -f assets/slim.jq --arg view issue   # single object too
#
# Handles three shapes: a top-level array, an {data|issues|…:[…]} envelope, or a
# single object. Pick a view with --arg view <issue|member|project|time|doc>.

def view:
  if   $view=="issue"   then {id, key, title, status, assignee_id, estimated_hours, priority}
  elif $view=="member"  then {user_id: (.user_id // .id), name: (.name // .email), role}
  elif $view=="project" then {id, key, name}
  elif $view=="time"    then {id, issue_id, user_id, duration_minutes, date}
  elif $view=="doc"     then {id, title, parent_doc_id, is_archived}
  else . end;

# Pull the array out of an envelope object, else null. Guards each access with a
# type check so it never throws on arrays/scalars.
def envelope:
  if type!="object" then null
  elif (.data|type=="array")     then .data
  elif (.issues|type=="array")   then .issues
  elif (.projects|type=="array") then .projects
  elif (.members|type=="array")  then .members
  elif (.entries|type=="array")  then .entries
  else null end;

if   type=="array"   then map(view)
elif envelope != null then (envelope | map(view))
else view end
