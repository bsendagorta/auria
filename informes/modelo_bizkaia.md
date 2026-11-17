# AURIA — Modelo mensual (bizkaia)
Generado: 2026-11-17 · datos desde 2021 · año de prueba: 2025

## Métricas en el año de prueba (menor = mejor)
| modelo   |    MAE |   desv_poisson |   total_real |   total_pred |
|:---------|-------:|---------------:|-------------:|-------------:|
| ref      | 16.102 |          8.087 |         6269 |      6076.25 |
| glm      | 16.3   |          7.719 |         6269 |      7124.29 |
| gbm      | 10.48  |          4.623 |         6269 |      6273.56 |

**Mejor modelo: gbm.** Si no es claramente mejor que `ref`, las variables aún no aportan.

## Totales del año de prueba por familia
| familia                    |   real |    ref |    glm |    gbm |   MAE_ref |   MAE_gbm |
|:---------------------------|-------:|-------:|-------:|-------:|----------:|----------:|
| ABEJAS_AVISPAS             |    978 |  764.5 | 1104.1 |  953.3 |      18.8 |       9.3 |
| GAS_MMPP                   |    216 |  167   |  225.8 |  183   |       4.6 |       4.6 |
| INCENDIO_FORESTAL_EXTERIOR |    886 |  658   | 1398.3 |  954.4 |      19   |      18.3 |
| INCENDIO_INDUSTRIAL        |    108 |  100.8 |  119.6 |  107.4 |       2.1 |       2.2 |
| INCENDIO_URBANO            |    711 | 1029.8 |  730.3 |  765.1 |      26.6 |       7.5 |
| METEO_ASISTENCIA           |    726 | 1006.8 |  688.5 |  809.5 |      50.2 |      26.7 |
| OTRAS_ASISTENCIAS          |    143 |  158   |  165.4 |  173.5 |       3   |       4.3 |
| OTROS                      |      0 |    0   |    0   |    0.1 |       0   |       0   |
| RESCATE_SALVAMENTO         |   2056 | 1696.5 | 2213.6 | 1857.3 |      30.4 |      23.8 |
| TRAFICO                    |    445 |  495   |  478.7 |  470.1 |       6.3 |       8.1 |

## Qué variables mueven cada familia (GLM, coeficientes estandarizados)
Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.

**RESCATE_SALVAMENTO**: idx_mes +0.17, lag_12 -0.17, log_media_hist_mes +0.11, dias_lluvia_30 +0.07, racha_max -0.07, hum_min_media +0.07

**INCENDIO_INDUSTRIAL**: lag_12 -0.12, media_3m_prev -0.12, racha_seca_max +0.12, mes_cos -0.11, nieve_total +0.10, mes_sin +0.10

**INCENDIO_FORESTAL_EXTERIOR**: idx_mes +0.37, hum_min_media -0.27, log_media_3m_prev +0.22, media_3m_prev +0.21, dias_navidad +0.21, dias_racha_60 -0.16

**INCENDIO_URBANO**: media_3m_prev +0.38, log_media_3m_prev -0.18, idx_mes -0.15, lluvia_total +0.14, log_media_hist_mes +0.13, racha_max -0.12

**TRAFICO**: tmax_media -0.12, dias_lluvia_10 +0.11, dias_lluvia_30 +0.10, mes_cos +0.10, dias_vacaciones_verano -0.09, racha_max -0.09

**GAS_MMPP**: dias_frio_5 +0.14, idx_mes +0.14, dias_festivo -0.11, dias_mes +0.10, dias_helada -0.10, hum_min_media +0.10

**ABEJAS_AVISPAS**: mes_sin -0.43, tmin_min +0.33, mes_cos -0.27, tmax_media +0.26, dias_viento_sur -0.26, idx_mes +0.25

**METEO_ASISTENCIA**: log_media_3m_prev +0.41, mes_cos -0.38, tmax_media +0.38, log_lag_12 +0.30, hum_min_media +0.29, tmin_min -0.29

**OTRAS_ASISTENCIAS**: dias_festivo -0.13, dias_finde +0.11, log_lag_12 -0.11, dias_navidad +0.11, dias_no_laborables -0.10, media_3m_prev +0.09