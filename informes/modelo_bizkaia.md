# AURIA — Modelo mensual (bizkaia)
Generado: 2026-11-17 · datos desde 2023 · año de prueba: 2025

## Métricas en el año de prueba (menor = mejor)
| modelo   |    MAE |   desv_poisson |   total_real |   total_pred |
|:---------|-------:|---------------:|-------------:|-------------:|
| ref      | 11.575 |          5.051 |         6269 |      6641    |
| glm      | 13.41  |          7.556 |         6269 |      6515.86 |
| gbm      | 12.518 |          6.744 |         6269 |      6228.25 |

**Mejor modelo: ref.** Si no es claramente mejor que `ref`, las variables aún no aportan.

## Totales del año de prueba por familia
| familia                    |   real |    ref |    glm |    gbm |   MAE_ref |   MAE_gbm |
|:---------------------------|-------:|-------:|-------:|-------:|----------:|----------:|
| ABEJAS_AVISPAS             |    978 | 1082.5 |  923.7 | 1038.3 |      16.1 |      19.7 |
| GAS_MMPP                   |    216 |  193   |  163.7 |  193.9 |       3.5 |       4.8 |
| INCENDIO_FORESTAL_EXTERIOR |    886 | 1003.5 |  826.9 |  828.4 |      13   |      14.9 |
| INCENDIO_INDUSTRIAL        |    108 |  110   |   97.3 |  126.5 |       2.5 |       3.2 |
| INCENDIO_URBANO            |    711 |  736.5 |  781.4 |  661.5 |       5.4 |       7.1 |
| METEO_ASISTENCIA           |    726 |  922   | 1049.6 |  811.8 |      40.2 |      39.9 |
| OTRAS_ASISTENCIAS          |    143 |  166.5 |  103.4 |  134.5 |       3.3 |       5   |
| OTROS                      |      0 |    0   |    0   |    0.3 |       0   |       0   |
| RESCATE_SALVAMENTO         |   2056 | 1900.5 | 2012.2 | 1926.3 |      22.5 |      22.4 |
| TRAFICO                    |    445 |  526.5 |  557.5 |  506.8 |       9.2 |       8.3 |

## Qué variables mueven cada familia (GLM, coeficientes estandarizados)
Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.

**RESCATE_SALVAMENTO**: log_media_3m_prev +0.14, media_3m_prev -0.12, mes_sin -0.10, mes_cos -0.10, dias_navidad +0.07, dias_puente -0.05

**INCENDIO_INDUSTRIAL**: dias_navidad +0.10, mes_sin +0.08, idx_mes -0.07, mes_cos -0.06, mes +0.06, media_3m_prev +0.05

**INCENDIO_FORESTAL_EXTERIOR**: dias_festivo +0.07, dias_no_laborables -0.07, idx_mes -0.07, media_3m_prev -0.06, dias_puente +0.05, mes_cos -0.04

**INCENDIO_URBANO**: mes_cos +0.13, dias_vacaciones_verano +0.08, log_media_3m_prev -0.06, dias_no_laborables -0.05, media_3m_prev +0.05, dias_mes +0.04

**TRAFICO**: mes +0.22, dias_puente -0.20, dias_navidad +0.19, mes_cos -0.14, lag_12 -0.09, media_hist_mes -0.09

**GAS_MMPP**: dias_navidad +0.11, log_media_3m_prev -0.09, idx_mes -0.09, mes_cos +0.09, dias_mes +0.08, dias_festivo -0.06

**ABEJAS_AVISPAS**: mes_cos -0.99, mes_sin -0.60, dias_navidad -0.35, log_media_3m_prev +0.35, dias_festivo +0.19, dias_no_laborables -0.14

**METEO_ASISTENCIA**: mes_cos +0.60, mes_sin -0.45, dias_puente -0.44, log_media_hist_mes -0.35, log_lag_12 -0.35, dias_no_laborables -0.22

**OTRAS_ASISTENCIAS**: idx_mes -0.16, dias_navidad +0.14, dias_festivo -0.14, mes_sin -0.13, log_media_3m_prev +0.13, dias_vacaciones_verano -0.11