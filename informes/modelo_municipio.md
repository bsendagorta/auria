# AURIA — Modelo mensual (municipio)
Generado: 2026-11-26 · datos desde 2023 · año de prueba: 2025

## Métricas en el año de prueba (menor = mejor)
| modelo   |   MAE |   desv_poisson |   total_real |   total_pred |
|:---------|------:|---------------:|-------------:|-------------:|
| ref      | 0.436 |          2.8   |         6269 |      6641.01 |
| glm      | 0.432 |          0.753 |         6269 |      6532.59 |
| gbm      | 0.39  |          0.657 |         6269 |      6210.88 |

**Mejor modelo: gbm.** Si no es claramente mejor que `ref`, las variables aún no aportan.

## Totales del año de prueba por familia
| familia                    |   real |    ref |    glm |    gbm |   MAE_ref |   MAE_gbm |
|:---------------------------|-------:|-------:|-------:|-------:|----------:|----------:|
| ABEJAS_AVISPAS             |    978 | 1082.5 |  973   | 1055.9 |       0.6 |       0.6 |
| GAS_MMPP                   |    216 |  193   |  241.4 |  202.7 |       0.2 |       0.2 |
| INCENDIO_FORESTAL_EXTERIOR |    886 | 1003.5 |  802.6 |  894.4 |       0.7 |       0.6 |
| INCENDIO_INDUSTRIAL        |    108 |  110   |   97.9 |  115.2 |       0.1 |       0.1 |
| INCENDIO_URBANO            |    711 |  736.5 |  907.1 |  762.9 |       0.5 |       0.5 |
| METEO_ASISTENCIA           |    726 |  922   |  895.5 |  695.3 |       0.7 |       0.5 |
| OTRAS_ASISTENCIAS          |    143 |  166.5 |   87.4 |  147.4 |       0.2 |       0.2 |
| OTROS                      |      0 |    0   |    0   |    0.5 |       0   |       0   |
| RESCATE_SALVAMENTO         |   2056 | 1900.5 | 1865.2 | 1856.9 |       1   |       0.9 |
| TRAFICO                    |    445 |  526.5 |  662.6 |  479.9 |       0.5 |       0.4 |

## Qué variables mueven cada familia (GLM, coeficientes estandarizados)
Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.

**RESCATE_SALVAMENTO**: mun_nivel +0.66, log_media_3m_prev +0.65, media_3m_prev -0.29, lluvia_total +0.23, dias_frio_5 +0.18, dias_lluvia_10 -0.16

**INCENDIO_INDUSTRIAL**: mun_nivel +0.47, log_media_3m_prev +0.43, media_3m_prev -0.18, dias_lluvia_30 -0.14, dias_lluvia_10 -0.12, lluvia_total +0.12

**INCENDIO_FORESTAL_EXTERIOR**: mun_nivel +0.56, log_media_3m_prev +0.40, racha_max +0.23, tmax_max -0.20, mes -0.20, dias_racha_60 -0.18

**INCENDIO_URBANO**: mun_nivel +0.63, log_media_3m_prev +0.50, dias_frio_5 +0.34, media_3m_prev -0.23, tmin_min +0.22, mes_cos +0.13

**TRAFICO**: dias_frio_5 -0.55, log_media_3m_prev +0.51, mes -0.44, dias_navidad +0.43, mun_nivel +0.40, dias_puente -0.37

**GAS_MMPP**: mun_nivel +0.81, log_media_3m_prev +0.46, media_3m_prev -0.35, dias_frio_5 +0.25, dias_mes +0.17, dias_racha_80 +0.12

**ABEJAS_AVISPAS**: log_media_3m_prev +0.66, mes_cos -0.60, tmax_media +0.42, mun_nivel +0.33, dias_viento_sur -0.23, media_3m_prev -0.23

**METEO_ASISTENCIA**: mun_nivel +0.65, log_media_3m_prev +0.39, mes_sin -0.36, dias_helada -0.34, dias_puente -0.34, tmax_media +0.26

**OTRAS_ASISTENCIAS**: mun_nivel +0.48, log_media_3m_prev +0.27, dias_navidad +0.23, idx_mes -0.20, dias_festivo -0.19, mes_sin -0.16