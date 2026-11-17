# AURIA — Modelo mensual (bizkaia)
Generado: 2026-11-17 · datos desde 2021 · año de prueba: 2025

## Métricas en el año de prueba (menor = mejor)
| modelo   |    MAE |   desv_poisson |   total_real |   total_pred |
|:---------|-------:|---------------:|-------------:|-------------:|
| ref      | 16.102 |          8.087 |         6269 |      6076.25 |
| glm      | 18.865 |         10.014 |         6269 |      7499.44 |
| gbm      | 11.592 |          4.905 |         6269 |      6275.36 |

**Mejor modelo: gbm.** Si no es claramente mejor que `ref`, las variables aún no aportan.

## Totales del año de prueba por familia
| familia                    |   real |    ref |    glm |    gbm |   MAE_ref |   MAE_gbm |
|:---------------------------|-------:|-------:|-------:|-------:|----------:|----------:|
| ABEJAS_AVISPAS             |    978 |  764.5 | 1209.3 |  978   |      18.8 |      12   |
| GAS_MMPP                   |    216 |  167   |  223.2 |  175.8 |       4.6 |       4.2 |
| INCENDIO_FORESTAL_EXTERIOR |    886 |  658   | 1567.7 |  919.5 |      19   |      19.8 |
| INCENDIO_INDUSTRIAL        |    108 |  100.8 |  114   |  104.4 |       2.1 |       2.3 |
| INCENDIO_URBANO            |    711 | 1029.8 |  549.8 |  728.1 |      26.6 |       7.9 |
| METEO_ASISTENCIA           |    726 | 1006.8 |  934.7 |  863.4 |      50.2 |      34.8 |
| OTRAS_ASISTENCIAS          |    143 |  158   |  161.5 |  162.3 |       3   |       3.3 |
| OTROS                      |      0 |    0   |    0   |    0.2 |       0   |       0   |
| RESCATE_SALVAMENTO         |   2056 | 1696.5 | 2210.5 | 1877.6 |      30.4 |      22.9 |
| TRAFICO                    |    445 |  495   |  528.7 |  465.9 |       6.3 |       8.7 |

## Qué variables mueven cada familia (GLM, coeficientes estandarizados)
Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.

**RESCATE_SALVAMENTO**: lag_12 -0.15, idx_mes +0.14, mes_cos -0.13, log_media_hist_mes +0.11, dias_navidad +0.08, mes_sin -0.06

**INCENDIO_INDUSTRIAL**: lag_12 -0.14, media_3m_prev -0.14, mes_cos -0.12, media_hist_mes -0.11, dias_puente -0.08, log_media_3m_prev +0.07

**INCENDIO_FORESTAL_EXTERIOR**: idx_mes +0.40, log_media_3m_prev +0.29, lag_12 -0.28, mes -0.24, log_media_hist_mes +0.21, dias_puente +0.15

**INCENDIO_URBANO**: media_3m_prev +0.33, idx_mes -0.27, log_media_3m_prev -0.22, log_media_hist_mes +0.19, lag_12 -0.15, mes_cos +0.09

**TRAFICO**: mes +0.19, log_media_hist_mes -0.17, dias_no_laborables +0.12, dias_finde -0.11, dias_vacaciones_verano -0.11, log_media_3m_prev +0.10

**GAS_MMPP**: dias_navidad +0.16, idx_mes +0.14, dias_festivo -0.14, dias_mes +0.08, media_3m_prev +0.04, mes_cos +0.04

**ABEJAS_AVISPAS**: mes_cos -0.90, mes_sin -0.60, log_media_3m_prev +0.56, dias_navidad -0.30, idx_mes +0.24, dias_puente +0.13

**METEO_ASISTENCIA**: log_media_3m_prev +0.56, media_3m_prev -0.50, log_lag_12 -0.50, lag_12 +0.32, mes_sin -0.29, dias_navidad +0.22

**OTRAS_ASISTENCIAS**: dias_festivo -0.11, mes_cos -0.11, dias_no_laborables -0.11, dias_finde +0.10, mes_sin -0.10, dias_navidad +0.08