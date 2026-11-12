select regionid,
       strptime(settlementdate, '%Y/%m/%d %H:%M:%S') as interval_end,
       fuel,
       cast(mw as double) as mw
from {{ source('raw', 'fuel_mix') }}
where regionid <> 'UNKNOWN'
qualify row_number() over (partition by regionid, settlementdate, fuel order by loaded_at desc) = 1
