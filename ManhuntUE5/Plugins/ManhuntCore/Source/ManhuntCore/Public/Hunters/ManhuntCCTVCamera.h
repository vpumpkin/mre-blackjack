// Ueberwachungskamera (Grossstadt, Einkaufszentrum, Casino). Der Hacker schaltet sich auf sie.
// Fab-Integration: Kamera-Mesh auf "Mesh" setzen, die "Camera"-Komponente zeigt die Blickrichtung.
// Die Kameras sind in World Partition IMMER geladen; beim Zuschauen streamt die Umgebung nach.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Camera/CameraComponent.h"
#include "ManhuntTypes.h"
#include "ManhuntCCTVCamera.generated.h"

class UStaticMeshComponent;
class UWorldPartitionStreamingSourceComponent;

UCLASS(Blueprintable)
class MANHUNTCORE_API AManhuntCCTVCamera : public AActor
{
	GENERATED_BODY()

public:
	AManhuntCCTVCamera();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CCTV") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CCTV") TObjectPtr<UStaticMeshComponent> Mesh;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CCTV") TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CCTV") TObjectPtr<UWorldPartitionStreamingSourceComponent> StreamingSource;

	/** Anzeigename im Hacker-HUD, z.B. "Mall EG Nord" oder "Casino Spielautomaten". */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CCTV") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CCTV") EManhuntBiome Biome = EManhuntBiome::City;
	/** Bis zu dieser Entfernung "sieht" die Kamera Runner (Netzwerk-Relevanz). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CCTV") float ViewDistance = 6000.f;
	/** Automatischer Schwenk (+- Grad) und Geschwindigkeit (Zyklen pro Sekunde). 0 = statisch. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CCTV") float SweepAngle = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CCTV") float SweepSpeed = 0.15f;

	FVector GetViewLocation() const { return Camera->GetComponentLocation(); }

	/** Nur auf dem Client des Hackers: Streaming-Quelle + Schwenk aktivieren. */
	void SetLocallyViewed(bool bViewed);

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	FRotator BaseRotation;
	float SweepTime = 0.f;
};
