// Hunter-Klasse 1: Der Hacker (Stadt-Aufklaerer).
// Schaltet per Handy auf alle Ueberwachungskameras und blaettert live durch.
// Trade-off: Solange er aufs Kamerabild schaut, kann er sich NICHT bewegen (serverseitige Sperre).
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ManhuntHackerComponent.generated.h"

class AManhuntCCTVCamera;
class AManhuntCharacter;

UCLASS(ClassGroup = (Manhunt), meta = (BlueprintSpawnableComponent))
class MANHUNTCORE_API UManhuntHackerComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UManhuntHackerComponent();

	UFUNCTION(BlueprintPure, Category = "Manhunt|Hacker") bool IsViewingCCTV() const { return ActiveCamera != nullptr; }
	UFUNCTION(BlueprintPure, Category = "Manhunt|Hacker") AManhuntCCTVCamera* GetActiveCamera() const { return ActiveCamera; }

	/** Lokal aufrufen (Input). */
	void RequestToggleCCTV();
	void RequestCycleCamera(int32 Direction);

	/** Server: Kamerabild sofort verlassen. */
	void StopViewing();

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UFUNCTION(Server, Reliable) void Server_ToggleCCTV();
	UFUNCTION(Server, Reliable) void Server_CycleCamera(int32 Direction);
	UFUNCTION() void OnRep_ActiveCamera();

	void SetActiveCamera(AManhuntCCTVCamera* NewCamera);
	void GatherCameras(TArray<AManhuntCCTVCamera*>& OutCameras) const;
	AManhuntCharacter* GetCharacter() const;

	UPROPERTY(ReplicatedUsing = OnRep_ActiveCamera) TObjectPtr<AManhuntCCTVCamera> ActiveCamera;

	/** Client: Kamera, deren Streaming-Quelle gerade lokal aktiv ist. */
	TWeakObjectPtr<AManhuntCCTVCamera> LocallyViewedCamera;
};
