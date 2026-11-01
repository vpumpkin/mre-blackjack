// Einfaches Canvas-HUD, damit alles ohne UMG sofort testbar ist:
// Matchzeit, Team/Klasse, Stamina, Geld/Pfandbon/Flaschen, Interaktions-Hinweis,
// Fortschrittsbalken, Nachrichten, Speedhunt-Alarm und das Taktik-Tablet der Hunter.
// Spaeter durch UMG-Widgets ersetzen (alle Werte sind BlueprintPure abrufbar).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "ManhuntHUD.generated.h"

class AManhuntPlayerController;

UCLASS()
class MANHUNTCORE_API AManhuntHUD : public AHUD
{
	GENERATED_BODY()

public:
	/** Halbe Kantenlaenge der Open World in cm (1,5 x 1,5 km = 75.000). */
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tablet") float MapHalfSize = 75000.f;
	UPROPERTY(EditDefaultsOnly, Category = "Manhunt|Tablet") FVector2D MapCenter = FVector2D::ZeroVector;

	virtual void DrawHUD() override;

protected:
	void DrawTextLine(const FString& Text, float X, float& Y, const FLinearColor& Color, float Scale = 1.f);
	void DrawBar(float X, float Y, float W, float H, float Ratio, const FLinearColor& Color);
	void DrawTablet(AManhuntPlayerController* PC, float X, float Y, float Size);
	FVector2D WorldToTablet(const FVector2D& World, float X, float Y, float Size) const;
};
