-- PREDISPATCHSEQNO = trading day (YYYYMMDD, starting 04:00) + period (01-48).
-- The run is issued at the start of that period: 04:00 + (period - 1) * 30 min.
select regionid,
       strptime(left(predispatchseqno, 8), '%Y%m%d')
           + interval 4 hour
           + (cast(right(predispatchseqno, 2) as integer) - 1) * interval 30 minute as issue_time,
       strptime(datetime, '%Y/%m/%d %H:%M:%S') as target_time,
       cast(totaldemand as double) as aemo_mw
from {{ source('raw', 'predispatch_regionsum') }}
where intervention = '0'
qualify row_number() over (
    partition by regionid, predispatchseqno, datetime order by loaded_at desc) = 1
