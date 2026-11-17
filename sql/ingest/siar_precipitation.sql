-- SiAR (MAPA's agro-weather network, its 519 active stations, listed below and in ref.stations as network 'siar') daily rain
-- -> embalses.obs.precipitation. Scheduled SQL, hourly; works 06:00-16:59 UTC only.
-- SiAR's limits: 1,000 requests and 10,000 records a day, and 100 records a MINUTE (enforced: 403). So each hourly run
-- asks for one chunk of 50 stations over the last two published days (<= 100 records): chunk = UTC hour - 6, eleven
-- chunks cover every station once a day (11 requests, ~1,040 records). Outside 06-16 UTC a run asks for nothing.
-- SiAR publishes a day late; the second day catches a late station. Its half-hourly data (~25,000 records a day) does
-- not fit the limits. The token comes from the catalog connection `siar` (kind query, prefix .../API/V1/Datos/), which
-- appends ?token=; the SQL never holds it. A SiAR day is the local (Europe/Madrid) calendar day.
-- A scheduled query cannot read ref.stations and a URL together, hence the list; a new SiAR station means a new list.
-- Rows repeat between runs: readers de-duplicate on (station_id, period_end_at, source).
WITH q AS (
  -- the 519 active stations of SiAR's Info/ESTACIONES (2026-11-17), 50 per chunk, as in ref.stations (network 'siar')
  SELECT * FROM (VALUES
         (0, 'Id=A02&Id=A03&Id=A04&Id=A05&Id=A06&Id=A08&Id=A09&Id=A10&Id=A101&Id=A102&Id=A1020&Id=A13&Id=A15&Id=A18&Id=A19&Id=A20&Id=A21&Id=AB02&Id=AB03&Id=AB05&Id=AB06&Id=AB07&Id=AB08&Id=AB09&Id=AB10&Id=AB11&Id=AB12&Id=AL01&Id=AL02&Id=AL04&Id=AL05&Id=AL06&Id=AL07&Id=AL08&Id=AL10&Id=AL11&Id=AL12&Id=AL201&Id=AV01&Id=AV101&Id=AV102&Id=BA01&Id=BA02&Id=BA04&Id=BA05&Id=BA06&Id=BA08&Id=BA09&Id=BA101&Id=BA102'),
         (1, 'Id=BA103&Id=BA104&Id=BA105&Id=BA106&Id=BA107&Id=BA108&Id=BA109&Id=BA203&Id=BA204&Id=BA205&Id=BA206&Id=BA210&Id=BU02&Id=BU03&Id=BU04&Id=BU05&Id=BU07&Id=BU101&Id=BU102&Id=C01&Id=C02&Id=CA01&Id=CA02&Id=CA04&Id=CA05&Id=CA06&Id=CA07&Id=CA10&Id=CA101&Id=CA11&Id=CC01&Id=CC04&Id=CC07&Id=CC09&Id=CC10&Id=CC101&Id=CC103&Id=CC104&Id=CC105&Id=CC107&Id=CC108&Id=CC109&Id=CC11&Id=CC12&Id=CC14&Id=CC16&Id=CC17&Id=CC18&Id=CC19&Id=CO01'),
         (2, 'Id=CO02&Id=CO04&Id=CO05&Id=CO06&Id=CO07&Id=CO08&Id=CO09&Id=CO101&Id=CO102&Id=CR01&Id=CR03&Id=CR04&Id=CR05&Id=CR07&Id=CR08&Id=CR09&Id=CR10&Id=CR11&Id=CS01&Id=CS03&Id=CS05&Id=CS07&Id=CS08&Id=CS09&Id=CS101&Id=CS11&Id=CS13&Id=CU01&Id=CU02&Id=CU03&Id=CU04&Id=CU05&Id=CU07&Id=CU08&Id=CU09&Id=GC01&Id=GC02&Id=GC03&Id=GC04&Id=GC05&Id=GC07&Id=GC09&Id=GC101&Id=GC103&Id=GC104&Id=GC105&Id=GC106&Id=GC107&Id=GC108&Id=GC109'),
         (3, 'Id=GC110&Id=GC111&Id=GC112&Id=GR01&Id=GR02&Id=GR03&Id=GR05&Id=GR06&Id=GR07&Id=GR08&Id=GR10&Id=GR101&Id=GR102&Id=GR11&Id=GR12&Id=GU02&Id=GU03&Id=GU05&Id=GU06&Id=GU09&Id=H02&Id=H03&Id=H05&Id=H06&Id=H07&Id=H08&Id=H09&Id=H10&Id=H101&Id=H102&Id=H103&Id=H107&Id=H11&Id=H12&Id=HU01&Id=HU02&Id=HU03&Id=HU04&Id=HU05&Id=HU06&Id=HU07&Id=HU08&Id=HU09&Id=HU10&Id=HU12&Id=HU13&Id=HU14&Id=HU15&Id=HU17&Id=HU18'),
         (4, 'Id=HU19&Id=HU20&Id=HU21&Id=HU22&Id=IB01&Id=IB02&Id=IB03&Id=IB04&Id=IB05&Id=IB06&Id=IB08&Id=IB10&Id=IB11&Id=J01&Id=J02&Id=J03&Id=J04&Id=J05&Id=J06&Id=J07&Id=J08&Id=J101&Id=J102&Id=J103&Id=J104&Id=J11&Id=J12&Id=J14&Id=J15&Id=J16&Id=LE01&Id=LE02&Id=LE03&Id=LE04&Id=LE05&Id=LE06&Id=LE07&Id=LE09&Id=LU01&Id=LU02&Id=M01&Id=M02&Id=M03&Id=M04&Id=M05&Id=M06&Id=M102&Id=MA01&Id=MA02&Id=MA04'),
         (5, 'Id=MA06&Id=MA07&Id=MA08&Id=MA09&Id=MA10&Id=MA101&Id=MA11&Id=MU01&Id=MU02&Id=MU03&Id=MU06&Id=MU08&Id=MU09&Id=MU10&Id=MU101&Id=MU102&Id=MU103&Id=MU104&Id=MU105&Id=MU106&Id=MU107&Id=MU108&Id=MU109&Id=MU11&Id=MU110&Id=MU111&Id=MU112&Id=MU114&Id=MU115&Id=MU117&Id=MU119&Id=MU120&Id=MU121&Id=MU123&Id=MU124&Id=MU125&Id=MU126&Id=MU128&Id=MU130&Id=MU14&Id=MU16&Id=MU17&Id=MU18&Id=MU19&Id=MU20&Id=MU21&Id=MU22&Id=NA02&Id=NA03&Id=NA04'),
         (6, 'Id=NA05&Id=NA06&Id=NA07&Id=NA08&Id=NA09&Id=NA10&Id=NA101&Id=NA102&Id=NA103&Id=NA104&Id=NA105&Id=NA106&Id=NA107&Id=NA108&Id=NA109&Id=NA11&Id=NA110&Id=NA111&Id=NA13&Id=NA14&Id=NA15&Id=NA16&Id=NA17&Id=NA18&Id=P01&Id=P02&Id=P03&Id=P04&Id=P06&Id=P07&Id=P08&Id=P101&Id=P102&Id=P103&Id=P104&Id=SA01&Id=SA03&Id=SA101&Id=SA102&Id=SE02&Id=SE03&Id=SE05&Id=SE07&Id=SE08&Id=SE09&Id=SE10&Id=SE101&Id=SE11&Id=SE12&Id=SE13'),
         (7, 'Id=SE15&Id=SE16&Id=SE17&Id=SE18&Id=SE19&Id=SE20&Id=SE21&Id=SE22&Id=SG01&Id=SG02&Id=SO01&Id=SO02&Id=SO03&Id=SO101&Id=TE01&Id=TE02&Id=TE03&Id=TE04&Id=TE05&Id=TE06&Id=TF02&Id=TF03&Id=TF04&Id=TF05&Id=TF06&Id=TF07&Id=TF08&Id=TF10&Id=TF101&Id=TF102&Id=TF105&Id=TF106&Id=TF107&Id=TF108&Id=TF109&Id=TF11&Id=TF110&Id=TF111&Id=TF112&Id=TF113&Id=TF114&Id=TF116&Id=TF117&Id=TF118&Id=TF119&Id=TF120&Id=TF121&Id=TF122&Id=TF123&Id=TF124'),
         (8, 'Id=TF125&Id=TF126&Id=TF127&Id=TF128&Id=TF129&Id=TF13&Id=TF130&Id=TF131&Id=TF132&Id=TF133&Id=TF134&Id=TF135&Id=TF136&Id=TF137&Id=TF138&Id=TF139&Id=TF14&Id=TF140&Id=TF142&Id=TF143&Id=TF144&Id=TF145&Id=TF146&Id=TF147&Id=TF148&Id=TF149&Id=TF150&Id=TF151&Id=TF152&Id=TF153&Id=TF154&Id=TF155&Id=TF156&Id=TF157&Id=TF158&Id=TF159&Id=TF160&Id=TF161&Id=TF162&Id=TF163&Id=TF164&Id=TF165&Id=TO01&Id=TO03&Id=TO04&Id=TO05&Id=TO07&Id=TO08&Id=TO09&Id=TO10'),
         (9, 'Id=TO11&Id=TO12&Id=V01&Id=V02&Id=V04&Id=V05&Id=V06&Id=V07&Id=V10&Id=V101&Id=V102&Id=V103&Id=V104&Id=V106&Id=V109&Id=V110&Id=V14&Id=V15&Id=V17&Id=V18&Id=V19&Id=V20&Id=V21&Id=V22&Id=V23&Id=V25&Id=V26&Id=V27&Id=V28&Id=V29&Id=V30&Id=VA01&Id=VA02&Id=VA03&Id=VA05&Id=VA06&Id=VA07&Id=VA08&Id=VA101&Id=VA102&Id=VA103&Id=VA104&Id=Z01&Id=Z02&Id=Z03&Id=Z04&Id=Z05&Id=Z06&Id=Z07&Id=Z08'),
         (10, 'Id=Z11&Id=Z14&Id=Z15&Id=Z16&Id=Z17&Id=Z18&Id=Z20&Id=Z21&Id=Z22&Id=Z23&Id=Z24&Id=Z25&Id=Z26&Id=ZA01&Id=ZA02&Id=ZA04&Id=ZA05&Id=ZA06&Id=ZA08')
  ) AS t(chunk, ids) WHERE chunk = hour(now() AT TIME ZONE 'UTC') - 6
),
r AS MATERIALIZED (
  SELECT (http_get('https://servicio.mapa.gob.es/siarapi/API/V1/Datos/Diarios/ESTACION?' || ids
                   || '&FechaInicial=' || strftime(current_date - 2, '%Y-%m-%d')
                   || '&FechaFinal=' || strftime(current_date - 1, '%Y-%m-%d'))).body AS txt
  FROM q
),
o AS (
  SELECT unnest(from_json(txt::JSON -> 'datos', '[{"Fecha":"VARCHAR","Estacion":"VARCHAR","Precipitacion":"DOUBLE"}]'),
                recursive := true)
  FROM r
)
SELECT 'siar:' || Estacion                                                              AS station_id,
       timezone('Europe/Madrid', strptime(Fecha, '%Y-%m-%dT%H:%M:%S'))                  AS period_start_at,
       timezone('Europe/Madrid', strptime(Fecha, '%Y-%m-%dT%H:%M:%S') + INTERVAL 1 DAY) AS period_end_at,
       1440                                                                             AS period_minutes,
       Precipitacion                                                                    AS precipitation_mm,
       true                                                                             AS is_provisional,
       'siar'                                                                           AS source
FROM o
WHERE Precipitacion IS NOT NULL
