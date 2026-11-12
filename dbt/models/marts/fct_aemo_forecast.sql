select regionid, issue_time, target_time, aemo_mw
from {{ ref('stg_aemo_forecast') }}
