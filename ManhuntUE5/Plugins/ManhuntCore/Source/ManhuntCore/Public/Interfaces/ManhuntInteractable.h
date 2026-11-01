// BPI_Interactable – alles, womit ein Spieler per [E] interagieren kann:
// Tueren, Fenster, Muelleimer, Pfandautomat, Kasse, Fahrzeuge, Drops ...
// Fab-Assets bekommen diese Funktion, indem ihr Blueprint das Interface implementiert
// (Class Settings -> Implemented Interfaces -> ManhuntInteractable) oder von einer
// fertigen C++-Basisklasse dieses Plugins erbt.
#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "ManhuntInteractable.generated.h"

class AManhuntCharacter;

UINTERFACE(MinimalAPI, Blueprintable)
class UManhuntInteractable : public UInterface
{
	GENERATED_BODY()
};

class MANHUNTCORE_API IManhuntInteractable
{
	GENERATED_BODY()

public:
	/** Server UND Client (Client nur fuer den UI-Hinweis). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Interaction")
	bool CanInteract(AManhuntCharacter* Interactor);

	/** Laeuft NUR auf dem Server (serverautoritativ). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Interaction")
	void Interact(AManhuntCharacter* Interactor);

	/** Text fuer den HUD-Hinweis, z.B. "Tuer oeffnen". */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Interaction")
	FText GetInteractionPrompt(AManhuntCharacter* Interactor);

	/** Server: laufende Interaktion abbrechen (Spieler gepackt, weggelaufen, aufgestiegen ...). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Manhunt|Interaction")
	void CancelInteraction(AManhuntCharacter* Interactor);
};
