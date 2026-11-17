# AURIA — Modelo mensual (municipio)
Generado: 2026-11-17 · datos desde 2023 · año de prueba: 2025

## Métricas en el año de prueba (menor = mejor)
| modelo   |   MAE |   desv_poisson |   total_real |   total_pred |
|:---------|------:|---------------:|-------------:|-------------:|
| ref      | 0.436 |          2.8   |         6269 |      6641.01 |
| glm      | 0.447 |          0.767 |         6269 |      6612.32 |
| gbm      | 0.397 |          0.677 |         6269 |      6225.98 |

**Mejor modelo: gbm.** Si no es claramente mejor que `ref`, las variables aún no aportan.

## Totales del año de prueba por familia
| familia                    |   real |    ref |    glm |    gbm |   MAE_ref |   MAE_gbm |
|:---------------------------|-------:|-------:|-------:|-------:|----------:|----------:|
| ABEJAS_AVISPAS             |    978 | 1082.5 |  808   |  800.9 |       0.6 |       0.6 |
| GAS_MMPP                   |    216 |  193   |  186.7 |  228.3 |       0.2 |       0.2 |
| INCENDIO_FORESTAL_EXTERIOR |    886 | 1003.5 |  888.6 |  907.6 |       0.7 |       0.6 |
| INCENDIO_INDUSTRIAL        |    108 |  110   |  106.7 |  116.7 |       0.1 |       0.1 |
| INCENDIO_URBANO            |    711 |  736.5 |  711.3 |  812.4 |       0.5 |       0.5 |
| METEO_ASISTENCIA           |    726 |  922   | 1129.4 |  860   |       0.7 |       0.6 |
| OTRAS_ASISTENCIAS          |    143 |  166.5 |  106.9 |  141.9 |       0.2 |       0.2 |
| OTROS                      |      0 |    0   |    0   |    0.4 |       0   |       0   |
| RESCATE_SALVAMENTO         |   2056 | 1900.5 | 1705.5 | 1838.6 |       1   |       0.9 |
| TRAFICO                    |    445 |  526.5 |  969.1 |  519.1 |       0.5 |       0.4 |

## Qué variables mueven cada familia (GLM, coeficientes estandarizados)
Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.

**RESCATE_SALVAMENTO**: log_media_3m_prev +0.64, mun_nivel +0.62, media_3m_prev -0.26, dias_no_laborables +0.16, mes_sin -0.14, dias_festivo -0.12

**INCENDIO_INDUSTRIAL**: mun_nivel +0.49, log_media_3m_prev +0.42, media_3m_prev -0.18, dias_navidad +0.12, media_hist_mes -0.11, lag_12 -0.11

**INCENDIO_FORESTAL_EXTERIOR**: mun_nivel +0.56, log_media_3m_prev +0.36, media_hist_mes -0.16, lag_12 -0.16, dias_no_laborables +0.15, mes -0.14

**INCENDIO_URBANO**: mun_nivel +0.59, log_media_3m_prev +0.52, media_3m_prev -0.22, mes_cos +0.16, dias_festivo -0.12, dias_vacaciones_verano +0.09

**TRAFICO**: log_media_3m_prev +0.54, mun_nivel +0.40, idx_mes +0.39, mes -0.29, media_hist_mes -0.24, lag_12 -0.24

**GAS_MMPP**: mun_nivel +0.79, log_media_3m_prev +0.47, media_3m_prev -0.35, dias_navidad +0.12, dias_mes +0.09, dias_festivo -0.09

**ABEJAS_AVISPAS**: mes_cos -0.98, log_media_3m_prev +0.69, mes_sin -0.59, dias_navidad -0.30, mun_nivel +0.29, media_3m_prev -0.23

**METEO_ASISTENCIA**: mun_nivel +0.69, mes_cos +0.63, log_media_3m_prev +0.36, dias_puente -0.28, mes_sin -0.27, dias_festivo -0.22

**OTRAS_ASISTENCIAS**: mun_nivel +0.51, log_media_3m_prev +0.29, dias_festivo -0.17, dias_navidad +0.16, media_hist_mes -0.16, lag_12 -0.16