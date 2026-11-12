-- All fetches are kept: the forecast job must only see forecasts fetched before its issue time.
select region as regionid,
       cast(time as timestamp) as time,
       cast(temperature_c as double) as temperature_c,
       kind,
       cast(fetched_at as timestamp) as fetched_at
from {{ source('raw', 'weather') }}
where temperature_c is not null
